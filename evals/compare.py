import argparse, json, os, statistics
from datetime import datetime, timezone

from evals import db
from evals.runner import load_cases
from evals.scorers import SIM_THRESHOLD

REPORT_DIR = db.ROOT / "evals" / "reports"
FRAGILE_MARGIN = 0.05

def _price(name: str) -> float:
    try:
        return float(os.getenv(name) or 0)
    except ValueError:
        return 0.0

PRICE_IN = _price("PRICE_IN_PER_M")     # $ per 1M input tokens
PRICE_OUT = _price("PRICE_OUT_PER_M")   # $ per 1M output tokens


def pick_run(conn, version: str, run_id: int | None = None) -> dict:
    if run_id:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    else:
        # latest run for this version that had no LLM errors (skips junk/rate-limited runs)
        row = conn.execute(
            """SELECT * FROM runs r WHERE prompt_version=? AND NOT EXISTS
               (SELECT 1 FROM results x WHERE x.run_id=r.id AND x.error IS NOT NULL)
               ORDER BY id DESC LIMIT 1""", (version,)).fetchone()
    if not row:
        raise SystemExit(f"No clean run found for prompt '{version}'. Run the suite first.")
    return dict(row)


def get_results(conn, run_id: int) -> dict[str, dict]:
    return {r["case_id"]: dict(r) for r in
            conn.execute("SELECT * FROM results WHERE run_id=?", (run_id,))}


def summarize(run: dict, results: dict) -> dict:
    lats = [r["latency_ms"] for r in results.values() if not r["error"] and r["latency_ms"]]
    pt = sum(r["prompt_tokens"] or 0 for r in results.values())
    ct = sum(r["completion_tokens"] or 0 for r in results.values())
    return {
        "run_id": run["id"], "prompt_version": run["prompt_version"], "model": run["model"],
        "mode": run["mode"], "total": run["total"], "passed": run["passed"],
        "pass_rate": run["pass_rate"], "critical_failed": run["critical_failed"],
        "median_latency_ms": round(statistics.median(lats), 1) if lats else 0,
        "max_latency_ms": round(max(lats), 1) if lats else 0,
        "prompt_tokens": pt, "completion_tokens": ct,
        "est_cost_usd": round((pt * PRICE_IN + ct * PRICE_OUT) / 1e6, 5),
    }


def compare(base: dict, cand: dict, cases: dict) -> dict:
    rows = []
    for cid, c in cand.items():
        b = base.get(cid)
        if c["error"]:
            status = "error"
        elif b is None:
            status = "new"
        elif b["passed"] and c["passed"]:
            status = "still_passing"
        elif not b["passed"] and c["passed"]:
            status = "fixed"
        elif b["passed"] and not c["passed"]:
            status = "broken"
        else:
            status = "still_failing"
        rows.append({"case_id": cid, "category": c["category"], "critical": bool(c["critical"]),
                     "question": c["question"], "status": status,
                     "baseline_answer": b["answer"] if b else None, "candidate_answer": c["answer"],
                     "candidate_detail": json.loads(c["rules_detail"] or "[]")})

    fragile = []
    for cid, c in cand.items():
        if c["similarity"] is not None and c["passed"]:
            min_sim = cases.get(cid, {}).get("min_similarity", SIM_THRESHOLD)
            if c["similarity"] - min_sim < FRAGILE_MARGIN:
                fragile.append({"case_id": cid, "similarity": c["similarity"], "threshold": min_sim})

    disagreements = [{"case_id": cid, "judge": c["judge_verdict"], "judge_reason": c["judge_reason"],
                      "rules_verdict": "pass" if c["passed"] else "fail"}
                     for cid, c in cand.items()
                     if c["judge_verdict"] in ("pass", "fail")
                     and (c["judge_verdict"] == "pass") != bool(c["passed"])]
    return {"cases": rows, "fragile": fragile, "judge_disagreements": disagreements}


def render_md(base_s: dict, cand_s: dict, diff: dict) -> str:
    rows = diff["cases"]
    by = lambda s: [r for r in rows if r["status"] == s]
    broken_crit = [r for r in by("broken") if r["critical"]]
    L = ["# Prompt comparison report", "",
         f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}_", "",
         f"**Baseline:** `{base_s['prompt_version']}` (run #{base_s['run_id']})  |  "
         f"**Candidate:** `{cand_s['prompt_version']}` (run #{cand_s['run_id']})  |  "
         f"**Model:** `{cand_s['model']}`  |  **Mode:** `{cand_s['mode']}`", "",
         "## Summary", "",
         "| Metric | Baseline | Candidate |", "|---|---|---|",
         f"| Pass rate | {base_s['pass_rate']:.1%} ({base_s['passed']}/{base_s['total']}) | "
         f"{cand_s['pass_rate']:.1%} ({cand_s['passed']}/{cand_s['total']}) |",
         f"| Critical failures | {base_s['critical_failed']} | {cand_s['critical_failed']} |",
         f"| Median latency (ms) | {base_s['median_latency_ms']} | {cand_s['median_latency_ms']} |",
         f"| Tokens (in / out) | {base_s['prompt_tokens']} / {base_s['completion_tokens']} | "
         f"{cand_s['prompt_tokens']} / {cand_s['completion_tokens']} |",
         f"| Est. cost (USD) | {base_s['est_cost_usd']} | {cand_s['est_cost_usd']} |", "",
         f"**Fixed:** {len(by('fixed'))}  |  **Broken:** {len(by('broken'))} "
         f"({len(broken_crit)} critical)  |  **Still failing:** {len(by('still_failing'))}  |  "
         f"**Still passing:** {len(by('still_passing'))}", ""]
    if PRICE_IN == 0 and PRICE_OUT == 0:
        L += ["> Cost shows 0 because `PRICE_IN_PER_M` / `PRICE_OUT_PER_M` are not set in `.env`.", ""]

    def section(title, status):
        items = by(status)
        if not items:
            return
        L.extend([f"## {title}", ""])
        for r in items:
            tag = " **[CRITICAL]**" if r["critical"] else ""
            L.append(f"- `{r['case_id']}`{tag} ({r['category']}): {r['question']}")
            if status in ("broken", "still_failing", "error"):
                L.append(f"  - candidate answer: {r['candidate_answer'][:160]!r}")
                L.append(f"  - why: {'; '.join(r['candidate_detail'])}")
            if status == "broken":
                L.append(f"  - baseline answer: {(r['baseline_answer'] or '')[:160]!r}")
        L.append("")

    section("Broken (regressions)", "broken")
    section("Fixed", "fixed")
    section("Still failing", "still_failing")
    section("Errors (infrastructure, not prompt quality)", "error")
    section("New cases (not in baseline)", "new")

    if diff["fragile"]:
        L += ["## Fragile passes (similarity within 0.05 of threshold)", ""]
        L += [f"- `{f['case_id']}`: similarity {f['similarity']} vs threshold {f['threshold']}"
              for f in diff["fragile"]] + [""]
    if diff["judge_disagreements"]:
        L += ["## Judge vs rules disagreements", ""]
        L += [f"- `{d['case_id']}`: rules={d['rules_verdict']}, judge={d['judge']} ({d['judge_reason']})"
              for d in diff["judge_disagreements"]] + [""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Compare two prompt versions")
    ap.add_argument("--baseline", default="v1")
    ap.add_argument("--candidate", default="v2")
    ap.add_argument("--baseline-run", type=int)
    ap.add_argument("--candidate-run", type=int)
    a = ap.parse_args()

    conn = db.connect()
    b_run, c_run = pick_run(conn, a.baseline, a.baseline_run), pick_run(conn, a.candidate, a.candidate_run)
    b_res, c_res = get_results(conn, b_run["id"]), get_results(conn, c_run["id"])
    cases = {c["id"]: c for c in load_cases()}

    base_s, cand_s = summarize(b_run, b_res), summarize(c_run, c_res)
    diff = compare(b_res, c_res, cases)
    payload = {"baseline": base_s, "candidate": cand_s, **diff}

    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / "latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (REPORT_DIR / "latest.md").write_text(render_md(base_s, cand_s, diff), encoding="utf-8")

    n = lambda s: sum(1 for r in diff["cases"] if r["status"] == s)
    print(f"{a.baseline} -> {a.candidate}: fixed {n('fixed')}, broken {n('broken')}, "
          f"still failing {n('still_failing')}, still passing {n('still_passing')}")
    print(f"Pass rate {base_s['pass_rate']:.1%} -> {cand_s['pass_rate']:.1%}. "
          f"Report: {REPORT_DIR / 'latest.md'}")


if __name__ == "__main__":
    main()