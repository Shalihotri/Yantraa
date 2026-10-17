"""Export the live gpt-6-luna experiment (from a local results DB) for the showcase.

    uv run python showcase/export_live.py [runs/yantraa.db]   # writes showcase/src/data/live.json

Reads one completed live experiment (OpenAI Decisions API) recorded on 2026-10-15
with yantraa-evidence 0.2 on the synthetic returns data. Only completed runs are
exported: synthetic cases, model probabilities, costs and traces. No keys, no
personal data. The cases are regenerated from the seeded generator (same content
as the data used for the run; case IDs used the 0.2 generator version string).
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

from yantraa_evidence.domains import returns

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "src" / "data" / "live.json"
BATCH = "b_20261015144858_24c5"  # 10 dev cases x 5 strategies, all completed
RERUN = "b_20261015155440_e880"  # the same 10 cases, selective only, run again later
COND = re.compile(r"(delivered|within_window|damaged) ([0-9.]+)")
SECRET = re.compile(r"sk-[A-Za-z0-9_\-]{6,}|Bearer\s+\S{6,}|OPENAI_API_KEY", re.I)


def label(s: str) -> str:
    return s.replace("_", " ").capitalize()


def timeline(run: dict) -> list[dict]:
    """Steps as events: plan (selector probabilities), check, judge (label + condition probabilities)."""
    out = []
    for s in run["steps"]:
        call = s.get("call") or {}
        if s["kind"] == "select":
            out.append({"type": "plan", "chosen": s["action"], "status": s["status"],
                        "options": call.get("probabilities")})
        elif s["kind"] == "fetch":
            out.append({"type": "check", "source": s["action"], "status": s["status"], "cost": s["retrieval_cost"]})
        else:
            conds = {k: float(v) for k, v in COND.findall(s["summary"])}
            out.append({"type": "judge", "action": s["action"], "probabilities": call.get("probabilities") or {},
                        "conditions": conds or None})
    return out


def main(db: Path) -> int:
    returns.GENERATOR_VERSION = "gen-1.0.0"  # reproduce the 0.2 case IDs (content is unchanged)
    cases = {c.case_id: c for c in returns.ReturnsDomain().generate(42)["dev"]}
    con = sqlite3.connect(db)
    runs = [json.loads(j) for (j,) in con.execute(
        "SELECT json FROM runs WHERE batch_id=? AND stop_reason='classifier_decided'", (BATCH,))]
    rerun = [json.loads(j) for (j,) in con.execute(
        "SELECT json FROM runs WHERE batch_id=? AND stop_reason='classifier_decided'", (RERUN,))]
    summary = json.loads(con.execute("SELECT summary FROM batches WHERE batch_id=?", (BATCH,)).fetchone()[0])
    assert len(runs) == 50 and not any(SECRET.search(json.dumps(r)) for r in runs + rerun)

    def graph(run_id: str) -> dict:
        nodes = [{"id": i, "kind": k, "data": json.loads(d)} for i, k, d in con.execute(
            "SELECT node_id, kind, data FROM graph_nodes WHERE run_id=?", (run_id,))]
        links = [{"src": s, "dst": d, "rel": r} for s, d, r in con.execute(
            "SELECT src, dst, rel FROM graph_links WHERE run_id=?", (run_id,))]
        for n in nodes:  # 0.2 field name -> 0.3
            if "item_id" in n["data"]:
                n["data"]["subject_id"] = n["data"].pop("item_id")
        return {"nodes": nodes, "links": links}

    by_case: dict[str, dict] = {}
    for r in sorted(runs, key=lambda r: r["case_id"]):
        c = cases[r["case_id"]]
        entry = by_case.setdefault(r["case_id"], {
            "id": r["case_id"], "scenario": c.scenario, "scenario_label": label(c.scenario), "request": c.request,
            "facts": c.initial_facts, "answer": c.oracle_action, "runs": {}})
        entry["runs"][r["strategy"]] = {
            "decision": r["terminal"]["action"], "correct": r["correct"], "stop_reason": r["stop_reason"],
            "fetch_count": r["fetch_count"], "costs": r["costs"], "timeline": timeline(r), "graph": graph(r["run_id"]),
        }
    data = {
        "model": "gpt-6-luna", "api": "OpenAI Decisions API", "date": "2026-10-15", "split": "dev",
        "n_cases": len(by_case), "cases": list(by_case.values()),
        "metrics": summary["metrics"], "paired": summary["paired_comparisons"],
        "rerun_selective": {"accuracy": sum(r["correct"] for r in rerun) / len(rerun),
                            "mean_retrievals": sum(r["fetch_count"] for r in rerun) / len(rerun), "n": len(rerun)},
    }
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB): {len(by_case)} cases x 5 strategies")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "runs" / "yantraa.db"))
