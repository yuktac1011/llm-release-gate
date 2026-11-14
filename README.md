# LLM Release Gate

A small system that stops a bad prompt change from reaching production. It runs a fixed test suite against a baseline prompt and a candidate prompt, scores both, diffs the results, and fails the pull request if the candidate is worse.

The feature under test is a customer-support FAQ answerer for a fictional product ("CloudNest"). The feature is deliberately small. The testing and gating machinery is the real project.

- **Answering model:** `openai/gpt-oss-20b` (Groq, OpenAI-compatible API)
- **Judge model:** `openai/gpt-oss-120b`
- **Suite:** 38 test cases across 6 categories
- **CI:** GitHub Actions, required status check on `main`

---

## My contribution
What I did myself:

- Scoped the task and turned the brief into a build plan and checklist.
- Created the repository, virtual environment and folder structure.
- Chose the LLM setup: Groq free tier, a small answerer model (so it makes mistakes worth catching) and a larger judge model.
- Created and rotated the API key, kept it out of git (`.env` ignored, `.env.example` committed), and made the repo public after checking history for secrets.
- Ran every experiment on the real model: prompt versions v1 to v5 and the deliberately broken prompt, then read the failures one by one.
- Decided which failures were test bugs and which were prompt problems. Examples: unicode hyphens breaking string rules, "cryptocurrencies" not matching "cryptocurrency", similarity scoring flagging correct short answers.
- Added held-out cases (G01 to G03) after tuning v5, to check the fix was not just fitted to one test.
- Opened the failing and passing demo PRs, turned on the required status check, and verified that merging is blocked.
- Ran the five acceptance tests, including the missing-API-key case, and recorded the results.
- Wrote the failure log from the real failures I saw.

## AI assistance

I used Claude (Anthropic) as a pair-programming assistant throughout. It drafted the first versions of the application code, the scorers, the runner, the compare and gate scripts, the dashboard and the CI workflow. It also proposed the initial test cases and the prompt versions. I reviewed the code, ran it, reported the output back, and we iterated on the failures together. Where AI suggested something that did not work (for example the first rewordings of the prompt for T05), the failure is recorded in `docs/failure-log.md`.

---

## How it works

```
prompts/v1.yaml, v2.yaml ...      app/faq.json
        |                              |
        +-------------> app/service.py (builds system prompt)
                               |
                        app/llm_client.py  (mock | openai_compat, retries, timeouts)
                               |
evals/tests.yaml --> evals/runner.py --> evals/scorers.py
                               |            rules | similarity | LLM judge
                               v
                      evals/results.db (SQLite: runs, results, response cache)
                        |                      |
              evals/compare.py          dashboard/ (FastAPI + HTML)
        fixed / broken / unchanged
                        |
                 evals/gate.py  --> exit 0 pass | 1 fail | 2 infrastructure
                        |
        .github/workflows/prompt-gate.yml (required check on PRs)
```

### Repo layout

| Path | Purpose |
|---|---|
| `app/` | The feature under test: FAQ, LLM client, FastAPI `/answer` endpoint |
| `prompts/` | Versioned prompt files (prompt text plus model settings). `PRODUCTION` names the released version |
| `evals/` | Test cases, scorers, runner, comparison, gate, SQLite storage |
| `dashboard/` | Run history, failed cases, diff between two runs |
| `.github/workflows/` | The PR gate |
| `docs/` | Failure log, acceptance tests |

---

## Quick start

```bash
git clone <this repo>
cd llm-release-gate
python -m venv .venv
#Linux :- source .venv/bin/activate     
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then edit .env
```

`.env` settings:

```
LLM_MODE=mock                      # mock | openai_compat
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=                       # your key; never commit this
PROMPT_VERSION=v1
JUDGE_MODEL=openai/gpt-oss-120b
PRICE_IN_PER_M=                    # optional, USD per 1M input tokens
PRICE_OUT_PER_M=                   # optional, USD per 1M output tokens
```

`LLM_MODE=mock` needs no key and no network. It is a deterministic fake whose behaviour depends on the prompt, so it exercises the whole pipeline for free. It is a smoke test, not evidence about prompt quality.

### Commands

```bash
# run the API
uvicorn app.main:app --reload

# run the suite against a prompt version
python -m evals.runner --prompt v1 --no-judge --delay 3

# compare two versions (writes evals/reports/latest.md and latest.json)
python -m evals.compare --baseline v1 --candidate v5

# the gate: exit 0 pass, 1 fail, 2 infrastructure problem
python -m evals.gate --baseline v1 --candidate v5

# dashboard
uvicorn dashboard.server:app --port 8001
```

Add `--no-cache` to force fresh model calls. Responses are cached by a hash of prompt, settings, FAQ and question, so repeat runs are free and identical.

---

## The test suite

38 cases in `evals/tests.yaml`. Each has a category, an expected behaviour, and a `critical` flag.

| Category | Count | What it checks |
|---|---|---|
| normal | 10 | Direct FAQ questions |
| paraphrase | 8 | Same facts, different wording |
| out_of_scope | 7 | Must refuse, must not invent policy |
| tricky | 5 | Answers that are "no", or near-misses of an FAQ rule |
| injection | 5 | Attempts to override instructions or leak the prompt |
| held-out (G) | 3 | Added after tuning v5, never used to tune it |

## Scoring

Three scorers, with different roles:

1. **Rule-based (hard gate).** Deterministic checks: must contain, must contain any of, must not contain, must refuse. Text is normalised first (non-breaking hyphens, curly quotes, narrow spaces) so rules match meaning and not typography. These decide pass or fail.
2. **Similarity (advisory by default).** Token recall plus sequence ratio against the reference FAQ answer. It only gates a case that sets `min_similarity` explicitly (currently P08). It is recorded for every case and used to flag fragile passes.
3. **LLM-as-judge (advisory).** A larger model grades the answer against the expected behaviour. Its verdict is stored and shown, and disagreements with the rules are reported. It does not decide pass or fail.

Why not gate on similarity: correct short answers scored low against a long reference. P02 ("The Pro plan is $9 per month.") scored 0.145 and would have blocked a good prompt.

## Gate rules

| Check | Result |
|---|---|
| More than 10% of candidate calls hit LLM errors | Exit 2 (infrastructure, not a verdict on the prompt) |
| A critical case that passed in baseline now fails | Fail |
| Pass rate below 90% (real-model runs) | Fail |
| Pass rate drops more than 5 points vs baseline | Fail |
| More than 2 non-critical cases broke | Fail |
| Otherwise | Pass |

Known failures that stay failing do not block, so the baseline's own flaws are not held against a candidate. All thresholds are arguments or environment variables (`GATE_MIN_PASS_RATE`, `GATE_MAX_DROP`, `GATE_MAX_BROKEN`).

---

## Prompt versions and results

Real model, temperature 0. v1 is production.

| Version | What changed | Result | Gate |
|---|---|---|---|
| v1 | Baseline: FAQ only, refuse otherwise, injection guard | 36/38 (94.7%). Fails T05, G01 (over-refusal) | baseline |
| v2 | Harmless wording change (tone, length) | 36/38. Same failures, 0 broken | Pass |
| v3 | Soft rewording to fix over-refusal | No change. T05 still fails | Pass (no effect) |
| v4 | Stronger topic-coverage wording | No change on T05 | no benefit |
| v5 | Worked example on an unrelated topic | 38/38. T05 and G01 fixed, 0 broken | Pass |
| v_bad | No scope limit, no injection guard | 32/38. Broken: O02, O03, O04, O06, I03, I04 (3 critical) | **Fail** |

v3 and v4 were measured on the earlier 35-case suite. The three held-out cases were added afterwards, and v5 passed all of them.

---

## CI

`.github/workflows/prompt-gate.yml` runs on pull requests that touch prompts, app code, evals or the workflow.

- It picks the production version from `prompts/PRODUCTION` and treats every prompt file added or modified in the PR as a candidate.
- **Released prompt files are immutable.** Editing the production prompt fails the job. Changes go in a new version file.
- With the `LLM_API_KEY` secret set, CI uses the real model. Without it (including fork PRs), CI runs in mock mode and the absolute pass-rate floor is switched off, because the mock is not accurate enough to be held to one.
- The verdict is written to the run summary and `evals/reports/` is uploaded as an artifact.
- The `gate` check is a required status check on `main`.

Demo PRs:

- Failing: `demo/bad-prompt` ([#1](https://github.com/yuktac1011/llm-release-gate/pull/1))
- Passing: `demo/good-prompt` ([#2](https://github.com/yuktac1011/llm-release-gate/pull/2))

The demo runs used mock mode. They prove the pipeline. The real-model evidence is the table above.

## Acceptance tests

See `docs/acceptance-tests.md`. All five pass: critical break fails CI, harmless wording change passes, out-of-scope questions are refused, injection does not change behaviour, missing API key gives a clear error with exit code 2.

---

## Reliability and reproducibility

- Temperature 0, versioned prompt files, a fixed test file, and a response cache keyed on everything that affects the answer.
- Timeouts, retries with backoff, and respect for the provider's `retry-after` header on rate limits.
- LLM errors are recorded separately from failed answers, so an outage never looks like a prompt regression.
- Missing key: clear error, stops on the first call, exit code 2.
- The judge never crashes a run. Any judge error is recorded and skipped.

## What the scoring cannot catch

- **Rules check presence of facts, not correctness of the whole answer.** An answer can contain "14 days" and still say something wrong around it.
- **Rules are wording-sensitive.** Several of my failures were test bugs, not model bugs (hyphen variants, plural forms, "9 am" vs "9am"). Each needed a human to read the answer and decide.
- **Similarity measures overlap, not truth.** Fragile passes are flagged, but a concise correct answer can still score low.
- **The judge is a model too.** It can be wrong or inconsistent, so it is advisory. Where the judge and rules disagreed during real evaluation, the judge caught semantic correctness that strict string matching missed (e.g., non-breaking hyphens in `AES‑256` or curly apostrophes in `can’t help` failing rigid substring checks while the judge recognized the answer was correct). Conversely, an advisory judge cannot be the sole gatekeeper because it introduces its own latency, token costs, and variance.
- **Small suite.** 38 cases, one run each at temperature 0. A pass rate here is not an accuracy claim.
- **Injection coverage is thin.** Five direct attacks do not make the prompt injection-proof.
- **The mock model is not evidence about prompt quality.** It only exercises the pipeline.
- **Tone and helpfulness are not measured.** A rude but accurate answer passes.
- **Cost is an estimate.** Free-tier runs cost nothing, and judge tokens are not included in the report.

## Failure analysis

See `docs/failure-log.md` for each failure, its root cause and the fix.

## Limitations

- Admins can bypass the required check. For a team, enable "Do not allow bypassing the above settings".
- The 90% floor, 5-point drop and 2-case tolerance are judgement calls, chosen so that noise does not block a good change while a critical regression always does.
- Free-tier rate limits make full real-model CI runs slow (several minutes).