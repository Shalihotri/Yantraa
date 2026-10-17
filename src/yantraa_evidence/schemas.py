"""Typed contracts shared by domains, tools, strategies, the runner, evaluation and storage.

Boundary rule: `Case` is the full record (includes hidden evidence and the answer key).
`Observation` is the only object a decision-maker ever sees; it is built from fetched
evidence alone and carries opaque references, never case IDs or scenario names.

Source IDs and decision labels are plain strings defined by each `Domain`, so the same
contracts serve product returns, insurance claims, credit reviews or anything else.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceStatus = Literal["unqueried", "ok", "unavailable", "link_rejected"]
STOP = "stop"  # the one non-source action a selector may choose


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- cases (your data)
class SourceRecord(Strict):
    """One backend record as stored in the case data (it may belong to another case or subject)."""

    record_id: str
    case_id: str
    subject_id: str | None = None
    captured_at: str
    effective_from: str | None = None
    effective_to: str | None = None
    version: str | None = None
    category: str | None = None
    payload: dict[str, Any]


class FixtureSource(Strict):
    available: bool = True
    records: list[SourceRecord] = Field(default_factory=list)


class Case(Strict):
    """One decision to make, with every record that *could* be checked and the correct answer."""

    case_id: str
    domain: str = ""
    split: str = "dev"
    scenario: str = ""  # situation label for slicing results (never shown to the decision-maker)
    template_id: str = ""
    generator_version: str = ""
    subject_id: str | None = None  # the thing the decision is about (item, claim, account...)
    request: str  # the incoming request, e.g. a customer message (may be inaccurate)
    initial_facts: dict[str, Any] = Field(default_factory=dict)
    hidden_evidence: dict[str, FixtureSource]
    oracle_action: str  # the answer key


# ---------------------------------------------------------------- runtime
class Evidence(Strict):
    evidence_id: str
    source_id: str
    case_ref: str
    subject_id: str | None = None
    captured_at: str
    effective_from: str | None = None
    effective_to: str | None = None
    version: str | None = None
    availability: Literal["available"] = "available"
    payload: dict[str, Any]


class Budgets(Strict):
    fetches: int
    selector_calls: int
    classifier_calls: int
    seconds: float
    spend_usd: float


class Observation(Strict):
    obs_ref: str
    request: str
    initial_facts: dict[str, Any]
    evidence: list[Evidence]
    source_status: dict[str, SourceStatus]
    remaining: Budgets
    legal_actions: list[str]


class ControllerDecision(Strict):
    next_action: str
    reason_code: str
    evidence_refs: list[str] = Field(default_factory=list)
    summary: str = Field(default="", max_length=300)


class TerminalDecision(Strict):
    action: str
    reason_code: str
    evidence_refs: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    summary: str = Field(default="", max_length=300)
    probabilities: dict[str, float] | None = None
    # Per-condition judgement (from Domain.conditions): probability it holds, None = unknown.
    condition_estimates: dict[str, float | None] | None = None


class CallRecord(Strict):
    role: Literal["selector", "classifier"]
    provider: str
    model: str
    model_version: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None  # None = price unknown (never assumed zero)
    simulated_latency_ms: float = 0.0
    elapsed_ms: float = 0.0
    probabilities: dict[str, float] | None = None
    ok: bool = True
    error: str | None = None


class Step(Strict):
    index: int
    kind: Literal["fetch", "select", "classify"]
    action: str
    status: str
    summary: str = ""
    reason_code: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    conditions: dict[str, float | None] | None = None
    retrieval_cost: float = 0.0
    simulated_latency_ms: float = 0.0
    call: CallRecord | None = None
    remaining: Budgets | None = None


class Costs(Strict):
    retrieval: float = 0.0
    model: float | None = 0.0
    decision_loss: float = 0.0
    total: float | None = 0.0


class RunResult(Strict):
    run_id: str
    batch_id: str | None = None
    domain: str
    case_id: str
    split: str
    scenario: str = ""
    strategy: str
    provider: str
    provider_label: str = ""  # who decided, e.g. "OpenAI Decisions API · gpt-6-luna"
    model: str
    model_version: str | None = None  # as reported by the provider on the last call
    config_hash: str
    seed: int
    trial: int = 0
    generator_version: str
    prompt_version: str
    status: Literal["completed", "unavailable"] = "completed"
    steps: list[Step]
    terminal: TerminalDecision
    stop_reason: str
    fetch_count: int
    costs: Costs
    wall_ms: float
    simulated_latency_ms: float
    oracle_action: str | None = None  # filled by the evaluator after termination
    correct: bool | None = None
    graph: dict[str, Any] = Field(default_factory=dict)
    created_at: str
