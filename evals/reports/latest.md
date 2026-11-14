# Prompt comparison report

_Generated 2026-11-14T06:06:41+00:00_

**Baseline:** `v1` (run #18)  |  **Candidate:** `v2` (run #21)  |  **Model:** `openai/gpt-oss-20b`  |  **Mode:** `openai_compat`

## Summary

| Metric | Baseline | Candidate |
|---|---|---|
| Pass rate | 94.7% (36/38) | 94.7% (36/38) |
| Critical failures | 1 | 1 |
| Median latency (ms) | 1288.4 | 1473.0 |
| Tokens (in / out) | 32934 / 4240 | 33162 / 4203 |
| Est. cost (USD) | 0.00374 | 0.00375 |

**Fixed:** 0  |  **Broken:** 0 (0 critical)  |  **Still failing:** 2  |  **Still passing:** 36

## Still failing

- `T05` **[CRITICAL]** (tricky): Can I get a refund 20 days after buying Pro?
  - candidate answer: "Sorry, I can only help with CloudNest support questions. I don't have information on that."
  - why: missing '14'
- `G01` (tricky): My reset link is 2 hours old, will it still work?
  - candidate answer: "Sorry, I can only help with CloudNest support questions. I don't have information on that."
  - why: missing '30 minutes'

## Fragile passes (similarity within 0.05 of threshold)

- `P02`: similarity 0.438 vs threshold 0.4
- `T03`: similarity 0.426 vs threshold 0.4
- `G02`: similarity 0.416 vs threshold 0.4
