# Design and method

This document explains how Yantraa Evidence works, what it measures, and the rules that keep its results honest.
Read it before citing a result.

## 1. The question

An AI that makes a decision (approve, deny, refer...) usually needs to check records first. Every check costs money
and time; every wrong decision costs more. **Can an AI that chooses which records to check reach the same decisions
at a lower total cost than checking everything?** Yantraa Evidence is a controlled test bed for that question, in any
domain where it applies.

## 2. Concepts

| Concept | What it is | Where |
|---|---|---|
| **Domain** | One kind of decision: its evidence sources (with costs), decision labels, a safe fallback label, default mistake penalties, and one rule (`assess`) that turns evidence into a decision. | `domain.py`, `domains/` |
| **Case** | One decision to make: the incoming request, initial facts, every record that *could* be checked (hidden), and the answer key. | `schemas.py` |
| **Strategy** | How evidence is gathered: which sources to check, in what order, and when to stop. | `strategies.py` |
| **Decision-maker** (provider) | Who chooses the next check and the final label: offline mock rules, or an AI model. | `adapters.py` |
| **Experiment** | A design (domain, cases, strategies, decision-maker, costs, limits) that is run, scored and saved. | `experiment.py` |
| **Report** | Metrics, paired comparisons against a baseline, penalty sensitivity, results by scenario, and every mistake. | `evaluate.py` |

## 3. Execution loop

For each case and strategy, the runner (`runner.py`):

1. Builds an **Observation**: the request, initial facts, *fetched* evidence only, the status of each source, and
   the remaining budget.
2. Restricts legal actions to sources not yet checked (within budget) plus `stop`.
3. Lets the strategy act: `fetch(source)`, `select()` (ask the decision-maker which source next), `classify()`
   (ask the shared decision-maker for the final label).
4. Validates every response. An unknown action, an unknown label, or malformed output ends the run.
5. Records a step-by-step trace with costs, timings, model version and the evidence cited.

**Limits** (per case, checked *before* each call): fetches, selector calls, classifier calls, seconds and a spend
cap. Exhaustion, invalid output, refusal or provider failure ends the run with the domain's **fallback** label and a
stop reason. There are no silent retries, no caching and no provider substitution.

## 4. Information boundary

- The decision-maker sees only the Observation. It never sees the answer key, scenario labels, case IDs or unfetched
  records. Run-scoped opaque references replace identifiers. Tests enforce this.
- Each source is checked at most once. An unavailable source returns a typed status, never an invented payload.
- Records owned by another case or subject are rejected and logged, never trusted (`Domain.admissible`).
- Contradictory records are kept as separate evidence, never merged.

## 5. Fair comparison

Every strategy shares the same final decision-maker, instructions and limits, so differences come from *which
evidence was checked*. The built-in strategies:

| Strategy | Behaviour | Role |
|---|---|---|
| `selective` | The decision-maker picks the next source, or stops. | the idea being tested |
| `fetch_all` | Check every source, then decide. | reference baseline |
| `fixed_order` | Checklist order; stop once the decision is no longer the fallback. | rule-based baseline |
| `confidence_threshold` | Checklist order; stop once the top probability reaches the threshold. Unavailable for providers without probabilities. | confidence baseline |
| `initial_only` | Decide from the request alone. | lower bound |

## 6. Scoring

**Total cost per case = retrieval cost + model cost + decision loss.**

- *Retrieval cost* is the simulated business cost of each check (per domain, overridable in config).
- *Model cost* comes from reported token usage and a versioned pricing file. A missing price makes model and total
  cost **unknown, never zero**.
- *Decision loss* is the penalty for choosing a label wrongly (per label, overridable). Defaults are illustrative
  assumptions, not measured business costs.

Reported per strategy: accuracy, wrong choices per label, fallback rate, mean checks, mean costs, simulated and
measured p50/p95 latency.

## 7. Statistics

- **Paired comparisons** against the reference baseline (default `fetch_all`) and against earlier experiments, by
  case, with **seeded bootstrap 95% intervals**. Repeated trials are averaged within a case before resampling.
- **Penalty sensitivity**: total cost recomputed with mistake penalties scaled ×0.25 to ×4 (the fallback penalty
  stays fixed), to show how fragile a conclusion is.
- Model-reported confidence is never treated as calibrated correctness. The simulator supports comparisons, not
  causal claims.

## 8. Data

- Case files are JSONL (`data/<domain>/<split>.jsonl`), one `Case` per line, with a manifest.
- The built-in `returns` domain generates 240 synthetic cases from a seeded, versioned generator: 120 `dev` and 120
  `test`, separated by message *template* before paraphrasing, so held-out messages are never rewordings of
  development messages. Outcomes are balanced for debugging; this is **not** a production distribution.
- Tune on `dev`. Keep `test` locked until a final run.
- All bundled data is synthetic and contains no real people, orders or personal information. If you bring your own
  data, anonymise it first and keep it out of version control (`private/` is git-ignored).

## 9. Reproducibility and storage

Every run stores the effective config hash, seed, generator and prompt versions, decision-maker label, reported
model version and full trace. Experiments are saved to SQLite (`runs/experiments.db`) together with an evidence graph
(case, subject, fetched records, evidence, decision; links such as *supports* / *contradicts*), and exported as
`metrics.csv`, `traces.jsonl` and `summary.json`. Only the fetched portion of a case becomes graph nodes; links come
from validated record metadata, never from generated text.

## 10. Decision-makers

| Provider | API | Probabilities | Notes |
|---|---|---|---|
| `mock` | none (domain rules) | simulated | Free and offline. Uses the same rule as the answer key, so mock accuracy is near-perfect by construction: it validates mechanics, not model quality. |
| `openai` | OpenAI Decisions API (beta) | yes | Selector is a `choice` over legal actions; classifier is a `choice` over labels plus one `predicate` per domain condition. |
| `openai-responses` | OpenAI Responses API | no | Structured output, `store=False`. |

Bring another model by implementing `select(obs)` and `classify(obs)` and passing `adapter_factory=` to an
Experiment.

## Change history

| Version | Date | Change |
|---|---|---|
| 0.1.0 | 2026-10-15 | First implementation: schemas, case tools, seeded generator, five strategies, guarded runner, paired bootstrap, SQLite evidence graph, CLI, tests. |
| 0.2.0 | 2026-10-15 | OpenAI Decisions API adapter; `.env` support; problems log. |
| 0.3.0 | 2026-10-17 | Package-first: pluggable domains and strategies; Overview / Experiment / Evaluate API and CLI; comparison against saved benchmarks; built-in web UI and server removed. |

## Implementation notes

1. **Policy version selection (returns domain).** The policy source returns only the version in force on the order's
   purchase date for the item's category. Versions that do not apply are not returned.
2. **Requirements come from the policy record (returns domain).** Without a fetched policy nothing can be resolved,
   so the result is the fallback. The answer key applies the same rule to complete case data.
3. **Forced stop without a model call.** When `stop` is the only legal action, the selector step is recorded as
   `forced` and no model call is made.
4. **Bundled defaults.** The wheel ships copies of `config/*.yaml` in `yantraa_evidence/defaults/`, so `pip install`
   works without a checkout. A test keeps the copies identical.
5. **`.env` support.** `load_config` reads `.env` in the working folder without overriding variables already set.

## Findings log

Early, small-sample observations, kept visible on purpose. No performance advantage is claimed.

- **2026-10-15, first live smoke run (`returns`, Decisions API, `gpt-6-luna`, 10 dev cases, 1 trial).** No provider
  errors. Most wrong decisions were in `conflicting_messages` cases, where the customer's message is inaccurate: the
  model's own condition predicates were about 1.0 for delivered, within window and damaged, but its final choice was
  `reject` (over-trusting the customer). `confidence_threshold` checked nothing on every case, because the model was
  already ≥0.85 confident in `escalate` before seeing evidence. `selective` checked all three sources on every case;
  its lower cost came from one fewer mistake. Ten cases is far too few for conclusions.
