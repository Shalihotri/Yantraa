# Changelog

## 0.3.0 (2026-10-17)

Package-first release: a toolkit you build on, not a fixed app.

- **Pluggable domains.** Sources, decision labels, fallback, penalties and the decision rule live in a `Domain`
  class. Product returns is now the built-in example (`domains/returns.py`); an insurance-claims domain is in
  `examples/`. Load custom domains by name, `module:ATTR` or `file.py:ATTR`.
- **Three-step API and CLI:** `overview()` / `yantraa overview`, `Experiment` / `yantraa experiment`,
  `evaluate()` + `compare_to_baseline()` / `yantraa evaluate`. The old `generate`, `run`, `benchmark`, `history`
  and `logs` commands are folded into these.
- **Custom strategies** with `@register_strategy`; custom decision-makers via `Experiment(adapter_factory=...)`.
- **Evaluate against saved benchmarks:** paired comparison of a new experiment against an earlier one.
- Generic metrics: `wrong_<label>` per decision label and `fallback_rate`. Loss is configured per label.
- Data moved to `data/<domain>/<split>.jsonl`; results to `runs/experiments.db`. Case fields renamed to be
  domain-neutral (`request`, `scenario`, `subject_id`). The regenerated returns data has the same content and answer
  keys as before.
- **Removed:** the React web UI, the FastAPI server and the `yantraa ui` command (`fastapi`/`uvicorn` dependencies
  dropped). Build your own UI on the Python API.
- CI: secret scanning; offline end-to-end runs for both domains.

## 0.2.0 (2026-10-15)

- Web UI served by a local server (removed in 0.3.0).
- OpenAI **Decisions API** (`gpt-6-luna`) as the preferred live decision-maker, with per-condition probabilities;
  the Responses API kept as a fallback.
- `.env` support and a problems log.
- Fix: no model call is made when `stop` is the only legal action.

## 0.1.0 (2026-10-15)

- First implementation: schemas, case tools, seeded generator, five strategies, budget-guarded runner, evaluation
  with paired bootstrap, SQLite evidence graph, CLI, tests.
