# Showcase

A static web page that shows what the `yantraa-evidence` package does, for people deciding whether it fits their
use case. It is **not part of the Python package**; `pip install yantraa-evidence` stays UI-free.

Live: https://shalihotri.github.io/Yantraa/

- **Overview**: the question, how it works, the three steps, first findings with a real model.
- **Explore a decision**: pick a request and a strategy, then watch the decision graph fill in check by check, with
  the probable outcome after each check, the result, its cost and the full trace.
- **Compare strategies**: cost per decision, paired differences vs checking everything (95% intervals), penalty
  sensitivity, the scoreboard, and the same result as `yantraa evaluate` prints it.
- **Fit your use case**: industries, personas and a domain in one Python class.

## Data

All data comes from the package itself, offline (mock decision-maker, no API key), and is committed as
`src/data/demo.json`. Regenerate it after changing the package:

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

Pushing changes under `showcase/` to `main` deploys it to GitHub Pages
([workflow](../.github/workflows/showcase.yml)).
