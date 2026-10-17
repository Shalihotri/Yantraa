# Contributing

Thanks for helping. This is a research toolkit, so **correctness and honesty of results come first**.

## Set up

```bash
uv sync                        # Python 3.11+, installs dev tools too
uv run pytest                  # all tests run offline, no API key needed
```

## Day-to-day loop

| Task | Command |
|---|---|
| See what's available | `uv run yantraa overview` |
| Run an experiment | `uv run yantraa experiment --limit 40` |
| Report / compare | `uv run yantraa evaluate` · `uv run yantraa evaluate NEW --against OLD` |
| Lint | `uv run ruff check src tests examples` |
| Tests | `uv run pytest` |
| Build the package | `uv build` |

## Adding things

- **A domain:** subclass `Domain` (see `examples/insurance_claims.py`). Built-in domains go in
  `src/yantraa_evidence/domains/` and are registered in `domains/__init__.py`. Add known-answer tests for `assess`.
- **A strategy:** a function decorated with `@register_strategy` in `strategies.py`, with a one-line docstring (it is
  shown in `yantraa overview`). Add a known-answer test.
- **A decision-maker:** a class with `select(obs)` and `classify(obs)` returning `(raw_dict, CallRecord)` in
  `adapters.py`. Never retry silently.

## Ground rules

1. **Never expose hidden evidence to a decision-maker.** `Observation` is the only thing it sees. If you add a field,
   add an isolation test (see `tests/test_core.py`).
2. **No silent retries, caching or provider substitution.** Failures return the fallback label with a stop reason and
   are logged.
3. **Unknown prices stay unknown**, never zero.
4. **Keep negative findings.** Don't tune on the test split. Record notable results in `docs/design.md` →
   *Findings log*.
5. **No secrets or personal data in commits.** Keys go in `.env` (git-ignored); use `.env.example` for new variables.
   Case data must be synthetic or properly anonymised. CI runs a secret scan.

## Pull requests

Keep them small, include tests, and describe *what changed in results* if a change affects scoring.
