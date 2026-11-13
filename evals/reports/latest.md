# Prompt comparison report

_Generated 2026-11-13T15:50:40+00:00_

**Baseline:** `v1` (run #11)  |  **Candidate:** `v4` (run #14)  |  **Model:** `openai/gpt-oss-20b`  |  **Mode:** `openai_compat`

## Summary

| Metric | Baseline | Candidate |
|---|---|---|
| Pass rate | 97.1% (34/35) | 94.3% (33/35) |
| Critical failures | 1 | 2 |
| Median latency (ms) | 1272.3 | 1353.8 |
| Tokens (in / out) | 30326 / 3889 | 33266 / 4171 |
| Est. cost (USD) | 0.00344 | 0.00375 |

**Fixed:** 0  |  **Broken:** 1 (1 critical)  |  **Still failing:** 1  |  **Still passing:** 33

## Broken (regressions)

- `T01` **[CRITICAL]** (tricky): Do you accept Bitcoin?
  - candidate answer: 'We accept Visa, Mastercard, UPI, and PayPal. Unfortunately, Bitcoin and other cryptocurrencies are not supported.'
  - why: none of ['not accept', "don't accept", 'cryptocurrency'] found
  - baseline answer: 'We don’t accept Bitcoin or any other cryptocurrency. We currently support Visa, Mastercard, UPI, and PayPal for payments. If you have any other payment question'

## Still failing

- `T05` **[CRITICAL]** (tricky): Can I get a refund 20 days after buying Pro?
  - candidate answer: "Sorry, I can only help with CloudNest support questions. I don't have information on that."
  - why: missing '14'

## Fragile passes (similarity within 0.05 of threshold)

- `P02`: similarity 0.438 vs threshold 0.4
- `T03`: similarity 0.429 vs threshold 0.4
