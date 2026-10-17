"""Export showcase data from the real package (offline, mock decision-maker, no API key).

    uv run python showcase/export_data.py      # writes showcase/src/data/demo.json

For each domain: every strategy runs on the whole test split (for the comparison
tab), and a sample of cases (two per scenario) is exported with full traces, the
evidence graph, and the decision-maker's probable outcome after each check.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from yantraa_evidence import Experiment, evaluate, get_domain
from yantraa_evidence.adapters import MockAdapter
from yantraa_evidence.config import for_domain, load_config, load_pricing
from yantraa_evidence.runner import Session
from yantraa_evidence.strategies import BUILT_IN, describe

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "src" / "data" / "demo.json"
DOMAINS = [
    ("returns", {"title": "Retail returns", "industry": "Retail / e-commerce"}),
    (str(ROOT / "examples" / "insurance_claims.py") + ":DOMAIN",
     {"title": "Insurance claims", "industry": "Insurance"}),
]
PER_SCENARIO = 2


def label(s: str) -> str:
    return s.replace("_", " ").capitalize()


def evolution(case, run, cfg, dom, pricing) -> list[dict]:
    """The mock decision-maker's view before any check and after each check, in the run's own order."""
    fetched = [st.action for st in run.steps if st.kind == "fetch"]
    adapter = MockAdapter(cfg, pricing, dom)
    s = Session(case, cfg, adapter, pricing, "showcase", dom)
    out = []
    for i in range(len(fetched) + 1):
        if i:
            s.fetch(fetched[i - 1])
        raw, _ = adapter.classify(s.observation())
        out.append({"after": fetched[i - 1] if i else None, "status": s.status[fetched[i - 1]] if i else None,
                    "probabilities": raw["probabilities"], "conditions": raw["condition_estimates"],
                    "leading": max(raw["probabilities"], key=raw["probabilities"].get)})
    return out


def readable(summary: str, stage: dict) -> str:
    """The mock's decision summary is a raw dict; say it in words instead."""
    if not summary.startswith("Conditions:") or not stage["conditions"]:
        return summary
    word = {1.0: "yes", 0.0: "no", None: "unknown"}
    parts = [f"{label(k)}: {word.get(v, v)}" for k, v in stage["conditions"].items()]
    return " · ".join(parts) + (" · conflicting records" if "Conflicts" in summary else "")


def export_domain(ref: str, meta: dict, tmp: Path) -> dict:
    cfg = load_config()
    cfg.data_dir, cfg.log_path = str(tmp / "data"), str(tmp / "log.jsonl")
    exp = Experiment(domain=ref, split="test", strategies=list(BUILT_IN), config=cfg, save=False)
    dom, ecfg = exp.dom, for_domain(exp.cfg, get_domain(ref))
    pricing = load_pricing(ecfg)
    cases = exp.load_cases()
    result = exp.run()
    report = evaluate(result, ecfg)

    picked, seen = [], {}
    for c in cases:
        if seen.get(c.scenario, 0) < PER_SCENARIO:
            seen[c.scenario] = seen.get(c.scenario, 0) + 1
            picked.append(c)
    picked.sort(key=lambda c: (list(seen).index(c.scenario), c.case_id))
    by_key = {(r.case_id, r.strategy): r for r in result.runs}

    showcase_cases = []
    for c in picked:
        runs = {}
        for strat in BUILT_IN:
            r = by_key[(c.case_id, strat)]
            runs[strat] = {
                "decision": r.terminal.action, "correct": r.correct, "stop_reason": r.stop_reason,
                "fetch_count": r.fetch_count, "costs": r.costs.model_dump(),
                "graph": r.graph, "evolution": evolution(c, r, ecfg, dom, pricing),
            }
            runs[strat]["steps"] = [
                {"kind": st.kind, "action": st.action, "status": st.status, "cost": st.retrieval_cost,
                 "summary": readable(st.summary, runs[strat]["evolution"][-1]) if st.kind == "classify" else st.summary}
                for st in r.steps]
        showcase_cases.append({"id": c.case_id, "scenario": c.scenario, "scenario_label": label(c.scenario),
                               "request": c.request, "facts": c.initial_facts, "answer": c.oracle_action,
                               "runs": runs})
    return {
        **meta, "name": dom.name, "task": dom.task, "fallback": dom.fallback, "subject_kind": dom.subject_kind,
        "sources": [{"id": s.id, "kind": s.kind, "description": s.description, "cost": ecfg.sources[s.id].cost}
                    for s in dom.sources],
        "actions": [{"id": k, "meaning": v} for k, v in dom.actions.items()],
        "conditions": [{"id": k, "meaning": v} for k, v in dom.conditions.items()],
        "loss": ecfg.loss,
        "cases": showcase_cases,
        "evaluation": {"text": f"$ yantraa evaluate\nExperiment {result.batch_id}\n\n" + report.to_text(),
                       "n_cases": report.n_cases, "reference": report.reference, "metrics": report.metrics,
                       "paired": report.paired_comparisons, "sensitivity": report.penalty_sensitivity,
                       "by_scenario": {s: {label(k): v for k, v in d.items()}
                                       for s, d in report.accuracy_by_scenario.items()}},
    }


def main() -> int:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:  # Windows keeps the log open
        domains = [export_domain(ref, meta, Path(tmp)) for ref, meta in DOMAINS]
    data = {"strategies": [{"id": s, "description": describe(s)} for s in BUILT_IN], "domains": domains}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB): "
          + ", ".join(f"{d['name']} {len(d['cases'])} cases" for d in domains))
    return 0


if __name__ == "__main__":
    sys.exit(main())
