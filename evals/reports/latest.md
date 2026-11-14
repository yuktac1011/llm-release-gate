# Prompt comparison report

_Generated 2026-11-14T20:11:20+00:00_

**Baseline:** `v1` (run #18)  |  **Candidate:** `v5` (run #20)  |  **Model:** `openai/gpt-oss-20b`  |  **Mode:** `openai_compat`

## Summary

| Metric | Baseline | Candidate |
|---|---|---|
| Pass rate | 94.7% (36/38) | 100.0% (38/38) |
| Critical failures | 1 | 0 |
| Median latency (ms) | 1288.4 | 1436.6 |
| Tokens (in / out) | 32934 / 4240 | 35822 / 4000 |
| Est. cost (USD) | 0.00374 | 0.00389 |

**Fixed:** 2  |  **Broken:** 0 (0 critical)  |  **Still failing:** 0  |  **Still passing:** 36

## Fixed

- `T05` **[CRITICAL]** (tricky): Can I get a refund 20 days after buying Pro?
- `G01` (tricky): My reset link is 2 hours old, will it still work?

## Fragile passes (similarity within 0.05 of threshold)

- `P02`: similarity 0.438 vs threshold 0.4
- `P07`: similarity 0.407 vs threshold 0.4
- `G01`: similarity 0.31 vs threshold 0.4
- `G02`: similarity 0.411 vs threshold 0.4
- `G03`: similarity 0.443 vs threshold 0.4
