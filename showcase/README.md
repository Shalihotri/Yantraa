# Showcase

An interactive, editorial-style page that shows what the `yantraa-evidence` package does, built around a real
model run. It is **not part of the Python package**: `pip install yantraa-evidence` stays UI-free.

Live: https://shalihotri.github.io/Yantraa/

| Section | What it shows |
|---|---|
| Hero | A real `gpt-6-luna` decision, replayed: every record checked, every condition met, and it still said reject |
| 01 The question | Total cost = checks + model calls + mistakes |
| 02 Watch a real model decide | 10 requests × 5 strategies: the evidence graph building up, the model's probabilities after each check, what it considered checking next, and the cost |
| 03 What we found | Three findings from the live run, each with its figure and caveats |
| 04 How it works | The loop, the information boundary, fail-safe limits, honest statistics |
| 05 At scale | Offline practice comparison on 120 requests, retail returns and insurance claims, plus `yantraa evaluate` output |
| 06 Your use case | Nine industries and who it helps |
| 07 Get started | Install, the three commands, a domain in one class |

## Data

Both files are committed and contain only synthetic cases, model probabilities, costs and traces.

- `src/data/live.json`: the live experiment (OpenAI Decisions API, `gpt-6-luna`, 10 dev requests, 5 strategies,
  2026-10-15). Exported once from a local results database with `export_live.py`; the database itself is not
  committed.
- `src/data/demo.json`: practice-mode comparisons, regenerated from the package at any time:

```bash
uv run python showcase/export_data.py      # from the repo root
```

## Develop and build

```bash
cd showcase
npm install
npm run dev        # http://localhost:5173
npm run build      # static site in showcase/dist
```

`public/og.png` is the 1200×630 link-preview image used by LinkedIn and others. Pushing changes under `showcase/`
to `main` deploys to GitHub Pages ([workflow](../.github/workflows/showcase.yml)).
