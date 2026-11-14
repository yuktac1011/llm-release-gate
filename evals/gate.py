import argparse, json, os, sys

from evals import db
from evals.compare import REPORT_DIR, compare, get_results, render_md, summarize
from evals.runner import load_cases

EXIT_PASS, EXIT_FAIL, EXIT_INFRA = 0, 1, 2


def emit(text: str) -> None:
    print(text)
    path = os.getenv("GITHUB_STEP_SUMMARY")  # shows up on the GitHub Actions run page
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def latest_run(conn, version: str) -> dict:
    row = conn.execute("SELECT * FROM runs WHERE prompt_version=? ORDER BY id DESC LIMIT 1",
                       (version,)).fetchone()
    if not row:
        emit(f"## Release gate: ERROR\n\nNo run found for prompt '{version}'. "
             f"Run `python -m evals.runner --prompt {version}` first.")
        sys.exit(EXIT_INFRA)
    return dict(row)


def error_count(results: dict) -> int:
    return sum(1 for r in results.values() if r["error"])


def main():
    ap = argparse.ArgumentParser(description="Release gate: exit 0 = pass, 1 = fail, 2 = infrastructure problem")
    ap.add_argument("--baseline", help="production prompt version (omit to check the floor only)")
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--min-pass-rate", type=float, default=float(os.getenv("GATE_MIN_PASS_RATE", "0.90")))
    ap.add_argument("--max-drop", type=float, default=float(os.getenv("GATE_MAX_DROP", "0.05")))
    ap.add_argument("--max-broken", type=int, default=int(os.getenv("GATE_MAX_BROKEN", "2")),
                    help="how many non-critical regressions are tolerated")
    ap.add_argument("--max-error-rate", type=float, default=0.10)
    a = ap.parse_args()

    conn = db.connect()
    cand_run = latest_run(conn, a.candidate)
    cand_res = get_results(conn, cand_run["id"])
    base_run = latest_run(conn, a.baseline) if a.baseline else None
    base_res = get_results(conn, base_run["id"]) if base_run else {}

    # 1) Infrastructure problems say nothing about prompt quality, so they never count as FAIL.
    infra = []
    for label, res in (("candidate", cand_res), ("baseline", base_res)):
        if label == "baseline" and not base_run:
            continue
        if not res or error_count(res) / len(res) > a.max_error_rate:
            infra.append(f"{label}: {error_count(res)}/{len(res)} cases hit LLM errors (rate limit, timeout or bad key)")
    if infra:
        emit("## Release gate: ERROR (infrastructure, not a prompt verdict)\n\n" +
             "\n".join(f"- {m}" for m in infra) + "\n\nRe-run the job. If it keeps happening, check the API key and rate limits.")
        sys.exit(EXIT_INFRA)

    cases = {c["id"]: c for c in load_cases()}
    cand_s = summarize(cand_run, cand_res)
    base_s = summarize(base_run, base_res) if base_run else None
    diff = compare(base_res, cand_res, cases)

    broken = [r for r in diff["cases"] if r["status"] == "broken"]
    fixed = [r for r in diff["cases"] if r["status"] == "fixed"]
    broken_crit = [r for r in broken if r["critical"]]

    # 2) The actual verdict
    reasons = []
    if cand_s["pass_rate"] < a.min_pass_rate:
        reasons.append(f"pass rate {cand_s['pass_rate']:.1%} is below the {a.min_pass_rate:.0%} floor")
    if base_s:
        if broken_crit:
            reasons.append("critical regression(s): " + ", ".join(r["case_id"] for r in broken_crit))
        drop = base_s["pass_rate"] - cand_s["pass_rate"]
        if drop > a.max_drop:
            reasons.append(f"pass rate dropped {drop:.1%} vs baseline (limit {a.max_drop:.0%})")
        non_crit = [r for r in broken if not r["critical"]]
        if len(non_crit) > a.max_broken:
            reasons.append(f"{len(non_crit)} non-critical cases broke (limit {a.max_broken}): " +
                           ", ".join(r["case_id"] for r in non_crit))

    verdict = "FAIL" if reasons else "PASS"
    head = f"Candidate `{a.candidate}`" + (f" vs baseline `{a.baseline}`" if base_s else " (no baseline: floor check only)")
    lines = [f"## Release gate: {verdict}", "", head, ""]
    lines += [f"- {r}" for r in reasons] or ["- all checks passed"]
    lines += ["", f"Pass rate: {cand_s['pass_rate']:.1%} ({cand_s['passed']}/{cand_s['total']})"
                  + (f", baseline {base_s['pass_rate']:.1%}" if base_s else "")
                  + f" | critical failures: {cand_s['critical_failed']}"]
    if broken:
        lines += ["", "Broken (passed in baseline, fails now):"]
        lines += [f"- `{r['case_id']}`{' [CRITICAL]' if r['critical'] else ''}: {r['question']}" for r in broken]
    if fixed:
        lines += ["", "Fixed:"] + [f"- `{r['case_id']}`: {r['question']}" for r in fixed]
    emit("\n".join(lines))

    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / "gate.json").write_text(json.dumps(
        {"verdict": verdict, "reasons": reasons, "candidate": cand_s, "baseline": base_s,
         "thresholds": {"min_pass_rate": a.min_pass_rate, "max_drop": a.max_drop, "max_broken": a.max_broken}},
        indent=2), encoding="utf-8")
    if base_s:
        (REPORT_DIR / "latest.json").write_text(json.dumps({"baseline": base_s, "candidate": cand_s, **diff}, indent=2), encoding="utf-8")
        (REPORT_DIR / "latest.md").write_text(render_md(base_s, cand_s, diff), encoding="utf-8")

    sys.exit(EXIT_FAIL if reasons else EXIT_PASS)


if __name__ == "__main__":
    main()