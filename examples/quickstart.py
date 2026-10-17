"""Overview -> Experiment -> Evaluate in one script. Offline, free, no API key.

    uv run python examples/quickstart.py
"""

from yantraa_evidence import Experiment, evaluate, overview, register_strategy
from yantraa_evidence.overview import to_text

# 1. Overview: what is available before designing anything.
print(to_text(overview()))


# 2. Experiment: add your own strategy next to the built-in ones, then run a small design.
@register_strategy
def cheapest_first(s):
    """Check sources from cheapest to most expensive; stop once the decision is no longer the fallback."""
    d = s.classify()
    for src in sorted(s.sources, key=lambda x: s.cfg.sources[x].cost):
        if d.action != s.domain.fallback:
            break
        s.fetch(src)
        d = s.classify()
    return d


exp = Experiment(domain="returns", split="dev", limit=40,
                 strategies=["selective", "cheapest_first", "fixed_order", "fetch_all"],
                 overrides={"loss": {"approve": 50}})  # your business: a wrong approval costs 50
print("\nWorst-case spend:", exp.estimate())
result = exp.run()

# 3. Evaluate: compare every strategy against the fetch_all benchmark.
report = evaluate(result)
print("\n" + report.to_text())
print(f"\nSaved as {result.batch_id}; exports in {result.export_dir}")
