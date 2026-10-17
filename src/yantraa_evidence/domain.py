"""Domains: everything that is specific to one kind of decision.

A domain declares its evidence sources (with default costs), its decision labels, the
safe fallback label, default mistake penalties and one rule, `assess`, that turns
evidence into a decision. The same rule produces the answer key (from complete case
data) and drives the offline mock decision-maker (from fetched evidence only), so the
two can never disagree on interpretation.

Everything else (runner, strategies, adapters, evaluation, storage) is domain-agnostic.

    class Claims(Domain):
        name = "claims"
        sources = (Source("get_policy", "Coverage status", cost=0.02), ...)
        actions = {"pay": "...", "deny": "...", "refer": "..."}
        fallback = "refer"
        loss = {"pay": 50, "deny": 10, "refer": 2}

        def assess(self, evidence): ...

    register_domain(Claims())
"""

from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .schemas import STOP, Case, SourceRecord

if TYPE_CHECKING:
    from .schemas import Evidence, Observation


@dataclass(frozen=True)
class Source:
    """One evidence source the decision-maker can check (at most once per case)."""

    id: str
    description: str  # shown to the AI when it chooses what to check
    cost: float = 0.0  # simulated business cost (USD) per check
    latency_ms: float = 0.0  # simulated latency per check
    kind: str = "Record"  # node kind in the evidence graph
    relation: str = "describes"  # graph link from a record to the case subject


@dataclass
class Assessment:
    """Three-valued result of a domain rule: conditions are True, False or None (unknown)."""

    action: str
    conditions: dict[str, bool | None] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


class Domain:
    """Base class for a decision domain. Subclass it and implement `assess`."""

    name: str = ""
    title: str = ""
    task: str = ""  # one or two sentences describing the decision (used in AI prompts)
    sources: tuple[Source, ...] = ()  # order matters: it is the checklist order for baselines
    actions: dict[str, str] = {}  # decision label -> meaning
    fallback: str = "escalate"  # safe label used when evidence is insufficient or a run fails
    conditions: dict[str, str] = {}  # optional named checks, for per-condition explanations
    loss: dict[str, float] = {}  # default penalty when this label is chosen wrongly
    subject_kind: str = "Subject"  # graph node kind of Case.subject_id
    select_prompt: str = ""  # optional prompt overrides; generic prompts are built otherwise
    classify_prompt: str = ""

    # ---------------------------------------------------------- required
    def assess(self, evidence: dict[str, list[dict]]) -> Assessment:
        """Decide from evidence payloads grouped by source ID. Absent sources are missing keys."""
        raise NotImplementedError

    # ---------------------------------------------------------- optional hooks
    def generate(self, seed: int = 42) -> dict[str, list[Case]]:
        """Synthetic cases by split. Domains without a generator use your own case files."""
        raise NotImplementedError(f"domain {self.name!r} has no generator; supply your own cases")

    def admissible(self, case: Case, source_id: str) -> tuple[list[SourceRecord] | None, list[str]]:
        """Validated records for one source: (records, or None if unavailable; rejected record IDs).

        Default: keep records owned by this case (and subject, when set). Override to add
        rules such as picking the policy version in force on a date.
        """
        src = case.hidden_evidence.get(source_id)
        if src is None or not src.available:
            return None, []
        owned = [r for r in src.records if r.case_id == case.case_id
                 and (case.subject_id is None or r.subject_id == case.subject_id)]
        return owned, [r.record_id for r in src.records if r not in owned]

    def mock_select(self, obs: Observation) -> tuple[str, str, str]:
        """(next_action, reason_code, summary) for the offline mock selector.

        Default: stop once the rule resolves, otherwise check the next source in order.
        """
        a = self.assess(group(obs.evidence))
        if a.action != self.fallback:
            return STOP, "resolved", f"Evidence already supports '{a.action}'."
        for s in self.source_ids:
            if s in obs.legal_actions:
                return s, f"need_{s}", f"{self.source(s).description} is not checked yet."
        return STOP, "no_useful_checks", "No remaining check can resolve the open conditions."

    def settled(self, obs: Observation, a: Assessment) -> bool:
        """True when more evidence cannot change the outcome (makes the mock confident in the fallback)."""
        return not any(s in obs.legal_actions for s in self.source_ids) or bool(a.conflicts)

    def evidence_relation(self, ev: Evidence, a: Assessment, action: str) -> str:
        """Graph link from a fetched record to the final decision ('supports', 'contradicts', 'informs')."""
        return "informs"

    # ---------------------------------------------------------- derived
    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(s.id for s in self.sources)

    def source(self, source_id: str) -> Source:
        return next(s for s in self.sources if s.id == source_id)

    def oracle(self, case: Case) -> str:
        """Answer key from complete case data. Unavailable required evidence gives the fallback."""
        found = {s: self.admissible(case, s)[0] for s in self.source_ids}
        return self.assess({s: [r.payload for r in recs] for s, recs in found.items() if recs}).action

    def validate(self) -> Domain:
        ids = self.source_ids
        problems = []
        if not self.name:
            problems.append("name is empty")
        if not ids or len(set(ids)) != len(ids) or STOP in ids:
            problems.append("sources must be non-empty, unique and must not use the reserved id 'stop'")
        if self.fallback not in self.actions:
            problems.append(f"fallback {self.fallback!r} is not one of the actions {list(self.actions)}")
        if set(self.loss) - set(self.actions):
            problems.append(f"loss has labels that are not actions: {sorted(set(self.loss) - set(self.actions))}")
        if problems:
            raise ValueError(f"invalid domain {self.name!r}: " + "; ".join(problems))
        return self

    def describe(self) -> dict:
        return {"name": self.name, "title": self.title, "task": self.task,
                "sources": [{"id": s.id, "description": s.description, "cost": s.cost, "latency_ms": s.latency_ms}
                            for s in self.sources],
                "actions": dict(self.actions), "fallback": self.fallback, "conditions": dict(self.conditions),
                "loss": dict(self.loss)}


def group(evidence: list[Evidence]) -> dict[str, list[dict]]:
    """Fetched evidence payloads grouped by source (the input shape of Domain.assess)."""
    out: dict[str, list[dict]] = {}
    for e in evidence:
        out.setdefault(e.source_id, []).append(e.payload)
    return out


# ------------------------------------------------------------------ registry
DOMAINS: dict[str, Domain] = {}


def register_domain(domain: Domain) -> Domain:
    DOMAINS[domain.name] = domain.validate()
    return domain


def get_domain(ref: str | Domain) -> Domain:
    """A registered name ('returns'), 'package.module:ATTR', or 'path/to/file.py:ATTR'."""
    if isinstance(ref, Domain):
        return ref.validate()
    if ref in DOMAINS:
        return DOMAINS[ref]
    if ":" in ref:
        target, attr = ref.rsplit(":", 1)
        if target.endswith(".py"):
            spec = importlib.util.spec_from_file_location(Path(target).stem, target)
            if spec is None or spec.loader is None:
                raise ValueError(f"cannot load domain file {target!r}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        else:
            module = importlib.import_module(target)
        obj = getattr(module, attr)
        return register_domain(obj() if isinstance(obj, type) else obj)
    raise KeyError(f"unknown domain {ref!r}; registered: {sorted(DOMAINS)}")
