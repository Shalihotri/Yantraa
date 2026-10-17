"""Case-data-backed evidence tools behind the same interface a live connector would use.

Each source is retrieved at most once per run. Unavailable sources return a typed
error, never an invented payload. Records that do not belong to this case/subject (or
that the domain rules out, e.g. a policy version not in force) are rejected, not trusted.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .logtracker import track
from .schemas import Case, Evidence, SourceStatus

if TYPE_CHECKING:
    from .config import AppConfig
    from .domain import Domain


class ToolError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class ToolResult:
    source: str
    status: SourceStatus
    evidence: list[Evidence] = field(default_factory=list)
    rejected_records: list[str] = field(default_factory=list)
    cost: float = 0.0
    latency_ms: float = 0.0


def opaque(*parts: str, prefix: str = "") -> str:
    return prefix + hashlib.sha256("|".join(parts).encode()).hexdigest()[:10]


class FixtureToolbox:
    """Serves evidence from a Case's hidden records. Swap for live connectors with the same `fetch`."""

    def __init__(self, case: Case, cfg: AppConfig, domain: Domain, case_ref: str):
        self.case, self.cfg, self.domain, self.case_ref = case, cfg, domain, case_ref
        self.queried: set[str] = set()

    def fetch(self, source: str) -> ToolResult:
        if source in self.queried:
            raise ToolError("repeated_fetch", f"{source} already retrieved for this case")
        if source not in self.cfg.sources:
            raise ToolError("unknown_source", source)
        self.queried.add(source)
        sc = self.cfg.sources[source]
        res = ToolResult(source, "unavailable", cost=sc.cost or 0.0, latency_ms=sc.latency_ms or 0.0)
        records, rejected = self.domain.admissible(self.case, source) if sc.available else (None, [])
        res.rejected_records = rejected
        if rejected:
            track("link_rejected", logging.WARNING, case_id=self.case.case_id, source=source, records=rejected)
        if records is None:
            return res
        if not records:
            res.status = "link_rejected"
            return res
        res.status = "ok"
        res.evidence = [
            Evidence(
                evidence_id=opaque(r.record_id, prefix="ev_"),
                source_id=source,
                case_ref=self.case_ref,
                subject_id=r.subject_id,
                captured_at=r.captured_at,
                effective_from=r.effective_from,
                effective_to=r.effective_to,
                version=r.version,
                payload=r.payload,
            )
            for r in records
        ]
        return res
