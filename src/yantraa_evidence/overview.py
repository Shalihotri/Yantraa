"""Overview: what is installed, configured and available, before you design an experiment.

    from yantraa_evidence import overview
    info = overview.overview()          # plain dict, ready for your own app or notebook
    print(overview.to_text(info))
"""

from __future__ import annotations

import os

from . import __version__, datasets, logtracker
from .adapters import PROVIDERS
from .config import AppConfig, for_domain, load_config
from .domain import DOMAINS, Domain, get_domain
from .strategies import STRATEGIES, describe


def overview(cfg: AppConfig | None = None, domain: str | Domain | None = None) -> dict:
    """Domains, strategies, decision-makers, effective settings, data status and recent problems."""
    base = cfg or load_config()
    dom = get_domain(domain or base.domain)
    eff = for_domain(base, dom)
    from .evaluate import saved_experiments

    try:
        saved = saved_experiments(eff)
    except Exception:  # an unreadable results DB should not hide the rest of the overview
        saved = []
    return {
        "version": __version__,
        "domain": dom.describe(),
        "domains": {n: d.title or n for n, d in sorted(DOMAINS.items())},
        "strategies": {n: describe(n) for n in STRATEGIES},
        "providers": PROVIDERS,
        "openai_key_present": bool(os.environ.get("OPENAI_API_KEY")),
        "settings": {
            "source_costs": {s: c.cost for s, c in eff.sources.items()},
            "loss": eff.loss,
            "limits": eff.limits.model_dump(),
            "confidence_threshold": eff.confidence_threshold,
            "reference_strategy": eff.reference_strategy,
            "config_hash": eff.hash(),
        },
        "data": {"dir": str(datasets.data_dir(eff, dom)), "splits": datasets.available_splits(eff, dom)},
        "results": {"db": str(eff.path(eff.db_path)), "saved_experiments": len(saved),
                    "latest": saved[0]["batch_id"] if saved else None},
        "recent_problems": logtracker.read(eff.path(eff.log_path), "WARNING", 5),
    }


def to_text(o: dict) -> str:
    d = o["domain"]
    lines = [f"Yantraa Evidence {o['version']}", "",
             f"Domain: {d['name']} - {d['title']}", f"  Task: {d['task']}", "  Evidence sources:"]
    lines += [f"    {s['id']:<18} cost {s['cost']:<6} {s['description']}" for s in d["sources"]]
    lines += ["  Decisions: " + ", ".join(d["actions"]) + f" (fallback: {d['fallback']})",
              "  Mistake penalties: " + ", ".join(f"{k} {v}" for k, v in o["settings"]["loss"].items()),
              "", "Registered domains: " + ", ".join(o["domains"]), "", "Strategies:"]
    lines += [f"  {k:<22} {v}" for k, v in o["strategies"].items()]
    lines += ["", "Decision-makers:"] + [f"  {k:<18} {v}" for k, v in o["providers"].items()]
    lines += [f"  OpenAI key found: {'yes' if o['openai_key_present'] else 'no (mock only)'}", ""]
    splits = o["data"]["splits"]
    lines += [f"Data: {o['data']['dir']}",
              "  " + (", ".join(f"{k}: {v} cases" for k, v in splits.items()) or "none yet (generated on first run)")]
    r = o["results"]
    lines += [f"Results: {r['saved_experiments']} saved experiment(s)" + (f", latest {r['latest']}" if r["latest"]
                                                                            else "")]
    if o["recent_problems"]:
        lines += ["", "Recent problems:"] + [f"  {p.get('ts', '')} {p.get('event')} {p.get('stop_reason', '')}"
                                             for p in o["recent_problems"]]
    return "\n".join(lines)
