"""Export practice-mode comparisons from the real package (offline, mock decision-maker, no API key).

    uv run python showcase/export_data.py      # writes showcase/src/data/demo.json

For each domain, every built-in strategy runs on the whole test split; the showcase
uses the domain description and the evaluation report (the "at scale" section).
Live model traces come from export_live.py.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from yantraa_evidence import Experiment, evaluate
from yantraa_evidence.strategies import BUILT_IN, describe

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "src" / "data" / "demo.json"
DOMAINS = [
    ("returns", {"title": "Retail returns", "industry": "Retail / e-commerce"}),
    (str(ROOT / "examples" / "insurance_claims.py") + ":DOMAIN",
     {"title": "Insurance claims", "industry": "Insurance"}),
]


def export_domain(ref: str, meta: dict, tmp: Path) -> dict:
    exp = Experiment(domain=ref, split="test", strategies=list(BUILT_IN), save=False, config=None)
    exp.cfg.data_dir, exp.cfg.log_path = str(tmp / "data"), str(tmp / "log.jsonl")
    dom, cfg = exp.dom, exp.cfg
    result = exp.run()
    report = evaluate(result, cfg)
    return {
        **meta, "name": dom.name, "task": dom.task, "fallback": dom.fallback, "subject_kind": dom.subject_kind,
        "sources": [{"id": s.id, "kind": s.kind, "description": s.description, "cost": cfg.sources[s.id].cost}
                    for s in dom.sources],
        "actions": [{"id": k, "meaning": v} for k, v in dom.actions.items()],
        "conditions": [{"id": k, "meaning": v} for k, v in dom.conditions.items()],
        "loss": cfg.loss,
        "evaluation": {"text": "$ yantraa evaluate\n" + report.to_text(), "n_cases": report.n_cases,
                       "reference": report.reference, "metrics": report.metrics,
                       "paired": report.paired_comparisons, "sensitivity": report.penalty_sensitivity},
    }


def main() -> int:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:  # Windows keeps the log open
        domains = [export_domain(ref, meta, Path(tmp)) for ref, meta in DOMAINS]
    data = {"strategies": [{"id": s, "description": describe(s)} for s in BUILT_IN], "domains": domains}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB): {', '.join(d['name'] for d in domains)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
