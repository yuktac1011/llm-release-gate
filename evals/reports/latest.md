# Prompt comparison report

_Generated 2026-11-13T14:47:06+00:00_

**Baseline:** `v1` (run #7)  |  **Candidate:** `v2` (run #8)  |  **Model:** `openai/gpt-oss-20b`  |  **Mode:** `openai_compat`

## Summary

| Metric | Baseline | Candidate |
|---|---|---|
| Pass rate | 97.1% (34/35) | 97.1% (34/35) |
| Critical failures | 1 | 1 |
| Median latency (ms) | 1272.3 | 1477.5 |
| Tokens (in / out) | 30326 / 3889 | 30536 / 3875 |
| Est. cost (USD) | 0.00344 | 0.00345 |

**Fixed:** 0  |  **Broken:** 0 (0 critical)  |  **Still failing:** 1  |  **Still passing:** 34

## Still failing

- `T05` **[CRITICAL]** (tricky): Can I get a refund 20 days after buying Pro?
  - candidate answer: "Sorry, I can only help with CloudNest support questions. I don't have information on that."
  - why: missing '14'; similarity 0.071 < 0.4

## Fragile passes (similarity within 0.05 of threshold)

- `P02`: similarity 0.438 vs threshold 0.4
- `T03`: similarity 0.426 vs threshold 0.4
