"""Evidence knowledge graph (in SQLite, no graph DB) and run persistence/exports.

Only the *fetched* portion of a case becomes graph nodes. Links are created from
validated record metadata, never from generated text; anything unvalidated stays
unlinked. Contradictory records remain separate nodes.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from .domain import group

if TYPE_CHECKING:
    from .domain import Domain
    from .schemas import Case, Evidence, RunResult


def build_graph(case: Case, evidence: list[Evidence], run: RunResult, domain: Domain) -> dict:
    """Case, subject, fetched records, evidence and the decision, with typed links."""
    ts, rid = run.created_at, run.run_id
    subject = case.subject_id
    nodes = [{"id": case.case_id, "kind": "Case", "data": {"split": case.split, "domain": domain.name}}]
    links = []
    if subject:
        nodes.append({"id": subject, "kind": domain.subject_kind, "data": {}})
        links.append({"src": case.case_id, "dst": subject, "rel": "concerns"})
    dec_id = "dec_" + rid
    a = domain.assess(group(evidence))
    for ev in evidence:
        src = domain.source(ev.source_id)
        rec_id = "src_" + ev.evidence_id[3:]
        nodes.append({"id": rec_id, "kind": src.kind, "data": {
            "version": ev.version, "effective_from": ev.effective_from, "effective_to": ev.effective_to}})
        nodes.append({"id": ev.evidence_id, "kind": "Evidence", "data": ev.model_dump(mode="json")})
        links.append({"src": ev.evidence_id, "dst": rec_id, "rel": "derived_from"})
        if subject and ev.subject_id == subject:  # ownership validated; otherwise the link stays unknown
            links.append({"src": rec_id, "dst": subject, "rel": src.relation})
        links.append({"src": ev.evidence_id, "dst": dec_id, "rel": domain.evidence_relation(ev, a, run.terminal.action),
                      "run_id": rid, "created_at": ts})
    nodes.append({"id": dec_id, "kind": "Decision", "data": {
        "run_id": rid, "action": run.terminal.action, "reason_code": run.terminal.reason_code,
        "evidence_refs": run.terminal.evidence_refs, "missing_requirements": run.terminal.missing_requirements,
        "created_at": ts}})
    return canonical({"nodes": nodes, "links": links})


def canonical(g: dict) -> dict:
    return {"nodes": sorted(g["nodes"], key=lambda n: n["id"]),
            "links": sorted(g["links"], key=lambda l: (l["src"], l["dst"], l["rel"]))}


# ------------------------------------------------------------------ SQLite
SCHEMA = """
CREATE TABLE IF NOT EXISTS batches(batch_id TEXT PRIMARY KEY, created_at TEXT, provider TEXT, split TEXT,
  strategies TEXT, config TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, batch_id TEXT, case_id TEXT, split TEXT, strategy TEXT,
  provider TEXT, terminal TEXT, stop_reason TEXT, created_at TEXT, json TEXT);
CREATE TABLE IF NOT EXISTS graph_nodes(run_id TEXT, node_id TEXT, kind TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS graph_links(run_id TEXT, src TEXT, dst TEXT, rel TEXT, link_run_id TEXT,
  created_at TEXT);
CREATE INDEX IF NOT EXISTS ix_runs_batch ON runs(batch_id);
CREATE INDEX IF NOT EXISTS ix_nodes_run ON graph_nodes(run_id);
CREATE INDEX IF NOT EXISTS ix_links_run ON graph_links(run_id);
"""


class Store:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.executescript(SCHEMA)

    def save_runs(self, runs: list[RunResult]) -> None:
        with self.db:
            for r in runs:
                self.db.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)", (
                    r.run_id, r.batch_id, r.case_id, r.split, r.strategy, r.provider, r.terminal.action,
                    r.stop_reason, r.created_at, r.model_copy(update={"graph": {}}).model_dump_json()))
                self.db.executemany("INSERT INTO graph_nodes VALUES (?,?,?,?)", [
                    (r.run_id, n["id"], n["kind"], json.dumps(n["data"], sort_keys=True)) for n in r.graph["nodes"]])
                self.db.executemany("INSERT INTO graph_links VALUES (?,?,?,?,?,?)", [
                    (r.run_id, l["src"], l["dst"], l["rel"], l.get("run_id"), l.get("created_at"))
                    for l in r.graph["links"]])

    def save_batch(self, batch_id, provider, split, strategies, config: dict, summary: dict) -> None:
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO batches VALUES (?,datetime('now'),?,?,?,?,?)", (
                batch_id, provider, split, json.dumps(strategies), json.dumps(config), json.dumps(summary,
                                                                                                    default=str)))

    def load_graph(self, run_id: str) -> dict:
        nodes = [{"id": i, "kind": k, "data": json.loads(d)} for i, k, d in self.db.execute(
            "SELECT node_id, kind, data FROM graph_nodes WHERE run_id=?", (run_id,))]
        links = []
        for s, d, rel, lrid, ts in self.db.execute(
                "SELECT src, dst, rel, link_run_id, created_at FROM graph_links WHERE run_id=?", (run_id,)):
            link = {"src": s, "dst": d, "rel": rel}
            if lrid is not None:
                link |= {"run_id": lrid, "created_at": ts}
            links.append(link)
        return canonical({"nodes": nodes, "links": links})

    def load_run(self, run_id: str) -> RunResult:
        from .schemas import RunResult

        (blob,) = self.db.execute("SELECT json FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return RunResult.model_validate_json(blob).model_copy(update={"graph": self.load_graph(run_id)})

    def batches(self) -> list[dict]:
        cols = ["batch_id", "created_at", "provider", "split", "strategies", "config", "summary"]
        return [dict(zip(cols, r)) for r in self.db.execute("SELECT * FROM batches ORDER BY created_at DESC")]

    def runs(self, batch_id: str | None = None, limit: int = 500) -> list[RunResult]:
        from .schemas import RunResult

        q, args = "SELECT json FROM runs", ()
        if batch_id:
            q, args = q + " WHERE batch_id=?", (batch_id,)
        rows = self.db.execute(q + " ORDER BY created_at DESC LIMIT ?", (*args, limit))
        return [RunResult.model_validate_json(b) for (b,) in rows]

    def single_runs(self, limit: int = 200) -> list[RunResult]:
        """Runs started one at a time (not part of an experiment batch), newest first."""
        from .schemas import RunResult

        rows = self.db.execute("SELECT json FROM runs WHERE batch_id IS NULL ORDER BY created_at DESC LIMIT ?",
                               (limit,))
        return [RunResult.model_validate_json(b) for (b,) in rows]


def export_batch(out_dir: Path, runs: list[RunResult], metric_rows: list[dict], extra: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if metric_rows:
        with open(out_dir / "metrics.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(metric_rows[0]))
            w.writeheader()
            w.writerows(metric_rows)
    with open(out_dir / "traces.jsonl", "w", encoding="utf-8") as f:
        for r in runs:
            f.write(r.model_dump_json() + "\n")
    (out_dir / "summary.json").write_text(json.dumps(extra, indent=2, default=str), encoding="utf-8")
    return out_dir
