"""Execution engine: build Observation -> restrict legal actions -> validate -> execute -> trace.

Every limit is checked *before* the call it guards. Any exhaustion, invalid output,
refusal or provider failure ends the run with the domain's fallback label (e.g.
`escalate`) and a stop reason; there are no silent retries and no provider substitution.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from pydantic import ValidationError

from .adapters import ProbabilitiesUnavailable, ProviderError, Refusal, describe_provider, make_adapter
from .config import AppConfig, for_domain, load_pricing, price_call
from .domain import Domain, get_domain
from .evaluate import score
from .logtracker import track
from .schemas import (
    STOP,
    Budgets,
    Case,
    ControllerDecision,
    Costs,
    Evidence,
    Observation,
    RunResult,
    SourceStatus,
    Step,
    TerminalDecision,
)
from .storage import build_graph
from .strategies import STRATEGIES, Strategy
from .tools import FixtureToolbox, ToolError, opaque


class StopRun(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason


class Session:
    """One case being decided: holds fetched evidence and enforces every limit. Strategies drive it."""

    def __init__(self, case: Case, cfg: AppConfig, adapter, pricing: dict, run_id: str, domain: Domain):
        self.case, self.adapter, self.pricing, self.run_id, self.domain = case, adapter, pricing, run_id, domain
        self.cfg = cfg = for_domain(cfg, domain)
        self.sources = domain.source_ids
        self.case_ref = opaque(case.case_id, run_id, prefix="cr_")  # run-scoped, unlinkable to case_id
        self.tools = FixtureToolbox(case, cfg, domain, self.case_ref)
        self.evidence: list[Evidence] = []
        self.status: dict[str, SourceStatus] = {t: "unqueried" for t in self.sources}
        self.steps: list[Step] = []
        self.calls = {"selector": 0, "classifier": 0}
        self.retrieval_cost = 0.0
        self.model_cost: float | None = 0.0
        self.sim_latency = 0.0
        self.t0 = time.perf_counter()

    # ---------------------------------------------------------- state
    def remaining(self) -> Budgets:
        L = self.cfg.limits
        spent = self.retrieval_cost + (self.model_cost or 0.0)
        return Budgets(fetches=L.max_fetches - self.fetch_count, selector_calls=L.max_selector_calls - self.calls[
            "selector"], classifier_calls=L.max_classifier_calls - self.calls["classifier"],
            seconds=round(L.max_seconds - self.elapsed(), 3), spend_usd=round(L.spend_cap_usd - spent, 6))

    @property
    def fetch_count(self) -> int:
        return sum(s != "unqueried" for s in self.status.values())

    def elapsed(self) -> float:
        return time.perf_counter() - self.t0

    def legal_actions(self) -> list:
        srcs = [t for t in self.sources if self.status[t] == "unqueried"] if self.remaining().fetches > 0 else []
        return [*srcs, STOP]

    def observation(self) -> Observation:
        return Observation(obs_ref=self.case_ref, request=self.case.request,
                           initial_facts=self.case.initial_facts, evidence=list(self.evidence),
                           source_status=dict(self.status), remaining=self.remaining(),
                           legal_actions=self.legal_actions())

    # ---------------------------------------------------------- guarded operations
    def _check_time(self):
        if self.elapsed() >= self.cfg.limits.max_seconds:
            raise StopRun("budget_time")

    def _check_spend(self, extra: float):
        if self.retrieval_cost + (self.model_cost or 0.0) + extra > self.cfg.limits.spend_cap_usd:
            raise StopRun("budget_spend", f"next call would exceed cap by estimate {extra:.4f}")

    def fetch(self, tool: str) -> None:
        self._check_time()
        if self.remaining().fetches <= 0:
            raise StopRun("budget_fetches")
        if tool not in self.legal_actions():
            raise StopRun("illegal_action", f"{tool} not legal now")
        self._check_spend(self.cfg.sources[tool].cost or 0.0)
        try:
            res = self.tools.fetch(tool)
        except ToolError as e:
            raise StopRun(e.code, str(e)) from e
        self.status[tool] = res.status
        self.evidence += res.evidence
        self.retrieval_cost += res.cost
        self.sim_latency += res.latency_ms
        self.steps.append(Step(index=len(self.steps), kind="fetch", action=tool, status=res.status,
                               evidence_ids=[e.evidence_id for e in res.evidence], retrieval_cost=res.cost,
                               simulated_latency_ms=res.latency_ms, remaining=self.remaining()))

    def _model_call(self, role: str):
        self._check_time()
        limit = getattr(self.cfg.limits, f"max_{role}_calls")
        if self.calls[role] >= limit:
            raise StopRun(f"budget_{role}")
        est = price_call(self.pricing, self.adapter.model, self.cfg.provider.est_input_tokens,
                         self.cfg.provider.est_output_tokens)
        if est is not None:
            self._check_spend(est)
        obs = self.observation()
        self.calls[role] += 1  # counted even if the call then fails
        try:
            raw, rec = getattr(self.adapter, "select" if role == "selector" else "classify")(obs)
        except Refusal as e:
            raise StopRun("refusal", str(e)) from e
        except ProviderError as e:
            raise StopRun("provider_error", str(e)) from e
        self.model_cost = None if (self.model_cost is None or rec.cost_usd is None) else self.model_cost + rec.cost_usd
        self.sim_latency += rec.simulated_latency_ms
        return obs, raw, rec

    def select(self) -> ControllerDecision:
        if self.legal_actions() == [STOP]:  # nothing to choose: don't spend a model call on it
            dec = ControllerDecision(next_action=STOP, reason_code="no_checks_left",
                                     summary="All allowed checks are done, so the run stops without asking the model.")
            self.steps.append(Step(index=len(self.steps), kind="select", action="stop", status="forced",
                                   summary=dec.summary, reason_code=dec.reason_code, remaining=self.remaining()))
            return dec
        obs, raw, rec = self._model_call("selector")
        step = Step(index=len(self.steps), kind="select", action=str(raw.get("next_action")), status="ok", call=rec)
        self.steps.append(step)
        try:
            dec = ControllerDecision.model_validate(raw)
        except ValidationError as e:
            step.status = "invalid_output"
            raise StopRun("invalid_output", str(e)[:300]) from e
        if dec.next_action not in obs.legal_actions:
            step.status = "illegal_action"
            raise StopRun("illegal_action", f"{dec.next_action} not in {obs.legal_actions}")
        step.summary, step.reason_code, step.evidence_ids = dec.summary, dec.reason_code, dec.evidence_refs
        step.remaining = self.remaining()
        return dec

    def classify(self) -> TerminalDecision:
        _, raw, rec = self._model_call("classifier")
        step = Step(index=len(self.steps), kind="classify", action=str(raw.get("action")), status="ok", call=rec)
        self.steps.append(step)
        try:
            dec = TerminalDecision.model_validate(raw)
        except ValidationError as e:
            step.status = "invalid_output"
            raise StopRun("invalid_output", str(e)[:300]) from e
        if dec.action not in self.domain.actions:
            step.status = "invalid_output"
            raise StopRun("invalid_output", f"{dec.action!r} is not one of {list(self.domain.actions)}")
        known = {e.evidence_id for e in self.evidence}
        dec.evidence_refs = [r for r in dec.evidence_refs if r in known]  # never trust uncited/invented refs
        step.summary, step.reason_code, step.evidence_ids = dec.summary, dec.reason_code, dec.evidence_refs
        step.conditions = dec.condition_estimates
        step.remaining = self.remaining()
        return dec


def run_case(case: Case, strategy: str | Strategy, cfg: AppConfig, provider: str = "mock",
             domain: str | Domain | None = None, seed: int | None = None, trial: int = 0,
             batch_id: str | None = None, adapter=None, pricing: dict | None = None) -> RunResult:
    """Decide one case with one strategy and return the scored, fully traced result."""
    domain = get_domain(domain or case.domain or cfg.domain)
    cfg = for_domain(cfg, domain)
    pricing = pricing or load_pricing(cfg)
    fn = STRATEGIES[strategy] if isinstance(strategy, str) else strategy
    name = strategy if isinstance(strategy, str) else fn.__name__
    run_id = "run_" + uuid.uuid4().hex[:12]
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status, stop_reason, err = "completed", "classifier_decided", ""
    try:
        adapter = adapter or make_adapter(provider, cfg, pricing, domain)
    except ProviderError as e:
        adapter = None
        stop_reason, err = "provider_error", str(e)
    s = Session(case, cfg, adapter, pricing, run_id, domain)
    terminal = None
    if adapter is not None:
        try:
            terminal = fn(s)
            if s.elapsed() > cfg.limits.max_seconds:  # a call that overran still falls back
                raise StopRun("budget_time", "limit exceeded during final call")
        except StopRun as e:
            stop_reason, err = e.reason, str(e)
        except ProbabilitiesUnavailable as e:
            status, stop_reason, err = "unavailable", "probabilities_unavailable", str(e)
    if terminal is None or stop_reason != "classifier_decided":
        terminal = TerminalDecision(action=domain.fallback, reason_code=stop_reason, summary=err[:300],
                                    evidence_refs=[e.evidence_id for e in s.evidence])
        track("run_escalated_by_failure", logging.WARNING, run_id=run_id, case_id=case.case_id, domain=domain.name,
              strategy=name, provider=provider, stop_reason=stop_reason, detail=err[:500])
    run = RunResult(
        run_id=run_id, batch_id=batch_id, domain=domain.name, case_id=case.case_id, split=case.split,
        scenario=case.scenario, strategy=name, provider=provider, provider_label=describe_provider(provider, cfg),
        model=getattr(adapter, "model", "n/a"),
        model_version=next((st.call.model_version for st in reversed(s.steps) if st.call), None),
        config_hash=cfg.hash(), seed=cfg.seed if seed is None else seed, trial=trial,
        generator_version=case.generator_version, prompt_version=cfg.prompt_version, status=status, steps=s.steps,
        terminal=terminal, stop_reason=stop_reason, fetch_count=s.fetch_count,
        costs=Costs(retrieval=round(s.retrieval_cost, 6), model=s.model_cost), wall_ms=s.elapsed() * 1000,
        simulated_latency_ms=s.sim_latency, created_at=created,
    )
    run = score(run, case, cfg)
    run.graph = build_graph(case, s.evidence, run, domain)
    return run


def estimate_spend(n_cases: int, strategies: list[str], cfg: AppConfig, provider: str,
                   domain: str | Domain | None = None) -> dict:
    """Upper-bound estimate (max calls x estimated tokens). Not a billing guarantee."""
    domain = get_domain(domain or cfg.domain)
    cfg = for_domain(cfg, domain)
    pricing = load_pricing(cfg)
    model = {"mock": cfg.provider.mock_model, "openai": f"decisions:{cfg.provider.decisions_model}"}.get(
        provider, cfg.provider.openai_model)
    per_call = price_call(pricing, model, cfg.provider.est_input_tokens, cfg.provider.est_output_tokens)
    L, n_src = cfg.limits, len(domain.sources)
    max_calls = {"initial_only": 1, "fetch_all": 1, "fixed_order": n_src,
                 "confidence_threshold": min(n_src + 1, L.max_classifier_calls), "selective": L.max_selector_calls + 1}
    calls = sum(max_calls.get(s, L.max_selector_calls + L.max_classifier_calls) for s in strategies) * n_cases
    return {"provider": provider, "model": model, "max_model_calls": calls,
            "max_model_spend_usd": None if per_call is None else round(calls * per_call, 4),
            "max_retrieval_usd": round(n_cases * len(strategies) * sum(t.cost or 0 for t in cfg.sources.values()), 4),
            "pricing_version": pricing.get("version")}


def run_batch(cases: list[Case], strategies: list[str], cfg: AppConfig, provider: str = "mock",
              domain: str | Domain | None = None, trials: int = 1, progress=None,
              adapter_factory=None) -> tuple[str, list[RunResult]]:
    """Every strategy on every case (x trials). adapter_factory() may supply a custom provider."""
    domain = get_domain(domain or cfg.domain)
    cfg = for_domain(cfg, domain)
    batch_id = "b_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:4]
    pricing = load_pricing(cfg)
    track("batch_start", batch_id=batch_id, domain=domain.name, provider=provider, strategies=strategies,
          n=len(cases))
    runs, total, done = [], len(cases) * len(strategies) * trials, 0
    for trial in range(trials):
        for strategy in strategies:
            for case in cases:
                runs.append(run_case(case, strategy, cfg, provider, domain, seed=cfg.seed + trial, trial=trial,
                                     batch_id=batch_id, pricing=pricing,
                                     adapter=adapter_factory() if adapter_factory else None))
                done += 1
                if progress:
                    progress(done / total)
    track("batch_end", batch_id=batch_id, runs=len(runs))
    return batch_id, runs
