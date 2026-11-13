import argparse, hashlib, json, os, sys, time
from datetime import datetime, timezone

import yaml

from app.llm_client import LLMError, MissingAPIKeyError
from app.service import ROOT, answer_question, load_faq, load_prompt
from evals import db
from evals.scorers import judge, score_rules, score_similarity

TESTS_PATH = ROOT / "evals" / "tests.yaml"


def load_cases() -> list[dict]:
    faq = {e["id"]: e["answer"] for e in load_faq()}
    if not TESTS_PATH.exists():
        sys.exit(f"ERROR: test file not found at {TESTS_PATH}")
    cases = yaml.safe_load(TESTS_PATH.read_text(encoding="utf-8"))
    if not cases:
        sys.exit(f"ERROR: {TESTS_PATH.name} is empty. Add test cases and save the file.")
    for c in cases:
        c["reference"] = faq.get(c.get("faq_id"), "")
    return cases


def cache_key(version: str, question: str) -> str:
    payload = json.dumps({"prompt": load_prompt(version), "faq": load_faq(), "q": question,
                          "mode": os.getenv("LLM_MODE"), "base": os.getenv("LLM_BASE_URL")},
                         sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def get_answer(conn, version: str, question: str, use_cache: bool) -> dict:
    # mock mode is free and instant, and its logic can change, so never cache it
    cacheable = use_cache and os.getenv("LLM_MODE", "mock") != "mock"
    key = cache_key(version, question)
    if cacheable:
        row = conn.execute("SELECT value FROM cache WHERE key=?", (key,)).fetchone()
        if row:
            return {**json.loads(row["value"]), "from_cache": 1}
    out = answer_question(question, version)
    if cacheable:
        conn.execute("INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)", (key, json.dumps(out)))
        conn.commit()
    return {**out, "from_cache": 0}


def run_suite(version: str, use_cache=True, use_judge=True, delay=0.0) -> dict:
    conn = db.connect()
    prompt = load_prompt(version)
    model_name = prompt["model"]["name"]
    results = []

    for case in load_cases():
        base = {"case_id": case["id"], "category": case["category"], "critical": int(case["critical"]),
                "question": case["question"], "error": None, "from_cache": 0,
                "latency_ms": 0, "prompt_tokens": 0, "completion_tokens": 0}
        try:
            out = get_answer(conn, version, case["question"], use_cache)
        except MissingAPIKeyError as e:
            print(f"\nERROR: {e}")
            sys.exit(2)
        except LLMError as e:
            results.append({**base, "answer": "", "passed": 0, "rules_passed": 0,
                            "rules_detail": json.dumps([f"LLM error: {e}"]), "similarity": None,
                            "judge_verdict": None, "judge_reason": None, "error": str(e)})
            continue

        answer = out["answer"]
        rules = score_rules(answer, case.get("rules", {}))

        # Similarity is always recorded, but only gates a case that sets min_similarity.
        sim, sim_ok, sim_note = None, True, []
        if case["reference"] and not case.get("rules", {}).get("refuse"):
            sim = score_similarity(answer, case["reference"])
            if "min_similarity" in case and sim < case["min_similarity"]:
                sim_ok = False
                sim_note = [f"similarity {sim} < {case['min_similarity']}"]

        j = judge(case, answer, case["reference"], model_name) if use_judge else \
            {"verdict": None, "reason": "judge disabled"}

        results.append({**base, "answer": answer, "passed": int(rules["passed"] and sim_ok),
                        "rules_passed": int(rules["passed"]),
                        "rules_detail": json.dumps(rules["failures"] + sim_note),
                        "similarity": sim, "judge_verdict": j["verdict"], "judge_reason": j["reason"],
                        "latency_ms": out["latency_ms"], "prompt_tokens": out["prompt_tokens"],
                        "completion_tokens": out["completion_tokens"], "from_cache": out["from_cache"]})
        if delay:
            time.sleep(delay)

    total = len(results)
    passed = sum(r["passed"] for r in results)
    meta = {"prompt_version": version, "model": model_name, "mode": os.getenv("LLM_MODE", "mock"),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total": total, "passed": passed, "pass_rate": round(passed / total, 4) if total else 0,
            "critical_failed": sum(1 for r in results if r["critical"] and not r["passed"]),
            "avg_latency_ms": round(sum(r["latency_ms"] for r in results) / total, 1) if total else 0,
            "prompt_tokens": sum(r["prompt_tokens"] for r in results),
            "completion_tokens": sum(r["completion_tokens"] for r in results)}
    meta["run_id"] = db.save_run(conn, meta, results)
    return {"meta": meta, "results": results}


def main():
    ap = argparse.ArgumentParser(description="Run the eval suite against a prompt version")
    ap.add_argument("--prompt", default="v1")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--delay", type=float, default=0.0, help="seconds between calls (rate limits)")
    a = ap.parse_args()

    out = run_suite(a.prompt, not a.no_cache, not a.no_judge, a.delay)
    m = out["meta"]
    for r in out["results"]:
        if not r["passed"]:
            tag = "CRITICAL " if r["critical"] else ""
            print(f"FAIL {tag}{r['case_id']}: {r['question']}\n     -> {r['answer'][:120]!r}\n     {r['rules_detail']}")

    errors = [r for r in out["results"] if r["error"]]
    if errors:
        print(f"\nWARNING: {len(errors)}/{m['total']} cases hit an LLM error. First error: {errors[0]['error']}")

    print(f"\nRun #{m['run_id']} | prompt={m['prompt_version']} | mode={m['mode']} | "
          f"passed {m['passed']}/{m['total']} ({m['pass_rate']:.0%}) | "
          f"critical failures: {m['critical_failed']} | avg latency {m['avg_latency_ms']} ms")


if __name__ == "__main__":
    main()