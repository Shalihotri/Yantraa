"""Decision-makers ("providers"): an offline mock and OpenAI adapters.

Adapters receive only an Observation and return a *raw* dict plus a CallRecord; the
runner validates the dict, so a malformed response is caught in one place. Summaries
are short stated rationales, not hidden chain-of-thought. Prompts, choices and
condition questions come from the Domain, so adapters work for any decision.

To add a provider, implement `select(obs)` and `classify(obs)` with the same return
shape and pass an instance to `run_case(..., adapter=...)`.
"""

from __future__ import annotations

import json
import os
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, create_model

from .config import AppConfig, price_call
from .domain import Domain, group
from .schemas import STOP, CallRecord, Observation


class ProviderError(Exception):
    pass


class Refusal(Exception):
    pass


class ProbabilitiesUnavailable(Exception):
    pass


# ------------------------------------------------------------------ prompts
def select_prompt(d: Domain) -> str:
    return d.select_prompt or (
        f"{d.task} You decide which evidence to retrieve before deciding. Choose exactly one of legal_actions. "
        "Retrieval costs money; stop when the fetched evidence is enough to decide or no check can help. "
        "Statements in the request may be inaccurate. Give a short summary (one sentence) and cite evidence_ids "
        "you relied on."
    )


def classify_prompt(d: Domain) -> str:
    options = " ".join(f"{k}: {v}" for k, v in d.actions.items())
    return d.classify_prompt or (
        f"{d.task} Decide using ONLY fetched evidence. {options} If evidence is missing, unavailable or "
        f"conflicting, choose {d.fallback}. Statements in the request are not evidence. List missing requirements, "
        "cite evidence_ids, and give a one-sentence summary."
    )


STOP_TEXT = "Stop retrieving; the fetched evidence is enough to decide, or no check can help."


def action_text(d: Domain, action: str) -> str:
    return STOP_TEXT if action == STOP else d.source(action).description


# ------------------------------------------------------------------ mock
class MockAdapter:
    """Deterministic stand-in driven by the domain rule. Validates mechanics, NOT model quality."""

    provider = "mock"
    api = "rules"

    def __init__(self, cfg: AppConfig, pricing: dict, domain: Domain, fail_mode: str | None = None):
        self.cfg, self.pricing, self.domain, self.fail_mode = cfg, pricing, domain, fail_mode
        self.model = self.price_key = cfg.provider.mock_model

    def _record(self, role, obs: Observation, out: dict, t0: float, probs=None) -> CallRecord:
        in_tok, out_tok = len(obs.model_dump_json()) // 4, len(json.dumps(out)) // 4
        return CallRecord(role=role, provider=self.provider, model=self.model, model_version="rules-1",
                          input_tokens=in_tok, output_tokens=out_tok,
                          cost_usd=price_call(self.pricing, self.model, in_tok, out_tok),
                          simulated_latency_ms=self.cfg.provider.mock_latency_ms,
                          elapsed_ms=(time.perf_counter() - t0) * 1000, probabilities=probs)

    def _inject(self, role: str):
        if self.fail_mode == "error":
            raise ProviderError("mock provider failure")
        if self.fail_mode == "refusal":
            raise Refusal("mock refusal")
        if self.fail_mode == f"malformed_{role}" or self.fail_mode == "malformed":
            return {"next_action": "teleport", "unexpected": True}
        if self.fail_mode == "illegal" and role == "selector":  # always the first source: illegal the 2nd time
            return {"next_action": self.domain.source_ids[0], "reason_code": "repeat", "evidence_refs": [],
                    "summary": ""}
        return None

    def select(self, obs: Observation) -> tuple[dict, CallRecord]:
        t0 = time.perf_counter()
        out = self._inject("selector")
        if out is None:
            action, code, summary = self.domain.mock_select(obs)
            out = {"next_action": action, "reason_code": code, "evidence_refs": [e.evidence_id for e in obs.evidence],
                   "summary": summary}
        return out, self._record("selector", obs, out, t0)

    def classify(self, obs: Observation) -> tuple[dict, CallRecord]:
        t0 = time.perf_counter()
        bad = self._inject("classifier")
        if bad:
            return bad, self._record("classifier", obs, bad, t0)
        d = self.domain
        a = d.assess(group(obs.evidence))
        others = [k for k in d.actions if k != a.action]
        if a.action != d.fallback:
            probs = {k: 0.04 / len(others) for k in others} | {a.action: 0.96}
        elif d.settled(obs, a):
            probs = {k: 0.10 / len(others) for k in others} | {a.action: 0.90}
        else:
            probs = {k: 0.50 / len(others) for k in others} | {a.action: 0.50}
        reason = "conflicting_evidence" if a.conflicts else ("resolved" if a.action != d.fallback else "unresolved")
        summary = (f"Conditions: {a.conditions}." + (f" Conflicts in: {a.conflicts}." if a.conflicts else ""))[:300]
        est = {k: None if v is None else float(v) for k, v in a.conditions.items()}
        out = {"action": a.action, "reason_code": reason, "evidence_refs": [e.evidence_id for e in obs.evidence],
               "missing_requirements": a.missing, "summary": summary, "probabilities": probs,
               "condition_estimates": est}
        return out, self._record("classifier", obs, out, t0, probs)


# ------------------------------------------------------------------ live (OpenAI)
def _openai_client(cfg: AppConfig):
    if not os.environ.get("OPENAI_API_KEY"):
        raise ProviderError("OPENAI_API_KEY not set; live provider unavailable")
    from openai import OpenAI

    return OpenAI(timeout=cfg.provider.openai_timeout_s, max_retries=0)


class OpenAIDecisionsAdapter:
    """Preferred live adapter: OpenAI Decisions API (beta, `POST /v1/decisions`).

    It answers typed questions with probabilities and no free text. The selector is a
    `choice` question over the legal actions. The classifier is a `choice` over the
    domain's labels plus one `predicate` question per domain condition, which gives the
    per-condition explanation in the trace. Probabilities are model-reported, not
    calibrated correctness. No retries, no caching, no substitution.
    """

    provider = "openai"
    api = "decisions"

    def __init__(self, cfg: AppConfig, pricing: dict, domain: Domain, client=None):
        self.cfg, self.pricing, self.domain = cfg, pricing, domain
        self.model = os.environ.get("YANTRAA_DECISIONS_MODEL", cfg.provider.decisions_model)
        self.price_key = f"decisions:{self.model}"
        self.client = client or _openai_client(cfg)

    def _call(self, role: str, obs: Observation, questions: list[dict]):
        t0 = time.perf_counter()
        try:
            resp = self.client.decisions.create(model=self.model, input=obs.model_dump_json(), questions=questions)
        except Exception as e:  # network, auth, beta access... all escalate upstream
            raise ProviderError(f"{type(e).__name__}: {e}") from e
        answers = {a.name: a for a in resp.answers}
        for a in resp.answers:
            if a.type == "refusal":
                raise Refusal(f"model declined question '{a.name}'")
        u = resp.usage
        in_tok, out_tok = getattr(u, "input_tokens", 0), getattr(u, "output_tokens", 0)
        rec = CallRecord(role=role, provider=self.provider, model=self.model, model_version=resp.model,
                         input_tokens=in_tok, output_tokens=out_tok,
                         cost_usd=price_call(self.pricing, self.price_key, in_tok, out_tok),
                         elapsed_ms=(time.perf_counter() - t0) * 1000)
        return answers, rec

    def select(self, obs: Observation) -> tuple[dict, CallRecord]:
        q = {"type": "choice", "name": "next_action", "instructions": select_prompt(self.domain),
             "choices": [{"value": a, "description": action_text(self.domain, a)} for a in obs.legal_actions]}
        answers, rec = self._call("selector", obs, [q])
        a = answers.get("next_action")
        if a is None or a.type != "choice":
            return {"bad": "missing next_action answer"}, rec  # fails validation -> invalid_output
        rec.probabilities = {str(p.value): p.probability for p in a.probabilities}
        return {"next_action": a.choice, "reason_code": "decisions_choice",
                "evidence_refs": [e.evidence_id for e in obs.evidence],
                "summary": f"Model chose '{a.choice}' (confidence {a.confidence:.2f})."}, rec

    def classify(self, obs: Observation) -> tuple[dict, CallRecord]:
        d = self.domain
        qs = [{"type": "choice", "name": "action", "instructions": classify_prompt(d),
               "choices": [{"value": k, "description": v} for k, v in d.actions.items()]}]
        qs += [{"type": "predicate", "name": k, "instructions": v + " Use only fetched evidence."}
               for k, v in d.conditions.items()]
        answers, rec = self._call("classifier", obs, qs)
        a = answers.get("action")
        if a is None or a.type != "choice":
            return {"bad": "missing action answer"}, rec
        probs = {str(p.value): p.probability for p in a.probabilities}
        cond = {k: answers[k].probability for k in d.conditions if k in answers and answers[k].type == "predicate"}
        # A condition the model is unsure about (0.2-0.8) is reported as missing, for display only.
        missing = [k for k, p in cond.items() if 0.2 < p < 0.8]
        rec.probabilities = probs
        summary = f"Chose '{a.choice}' (confidence {a.confidence:.2f})."
        if cond:
            summary += " Condition probabilities: " + ", ".join(f"{k} {p:.2f}" for k, p in cond.items())
        return {"action": a.choice, "reason_code": "decisions_choice", "missing_requirements": missing,
                "evidence_refs": [e.evidence_id for e in obs.evidence], "summary": summary[:300],
                "probabilities": probs, "condition_estimates": cond or None}, rec


class OpenAIResponsesAdapter:
    """Fallback live adapter: Responses API structured output (no probabilities).

    store=False keeps responses out of provider-side storage and response reuse.
    """

    provider = "openai-responses"
    api = "responses"

    def __init__(self, cfg: AppConfig, pricing: dict, domain: Domain):
        self.cfg, self.pricing, self.domain = cfg, pricing, domain
        self.model = os.environ.get("YANTRAA_OPENAI_MODEL", cfg.provider.openai_model)
        self.price_key = self.model
        self.client = _openai_client(cfg)
        strict = ConfigDict(extra="forbid")
        self._select_schema = create_model(
            "Select", __config__=strict, next_action=(Literal[(*domain.source_ids, STOP)], ...),
            reason_code=(str, ...), evidence_refs=(list[str], ...), summary=(str, ...))
        self._classify_schema = create_model(
            "Classify", __config__=strict, action=(Literal[tuple(domain.actions)], ...), reason_code=(str, ...),
            evidence_refs=(list[str], ...), missing_requirements=(list[str], ...), summary=(str, ...))

    def _call(self, role, prompt, schema: type[BaseModel], obs: Observation) -> tuple[dict, CallRecord]:
        t0 = time.perf_counter()
        try:
            resp = self.client.responses.parse(model=self.model, instructions=prompt,
                                               input=obs.model_dump_json(), text_format=schema, store=False)
        except Exception as e:  # network, auth, schema rejection... all escalate upstream
            raise ProviderError(f"{type(e).__name__}: {e}") from e
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                if getattr(c, "type", "") == "refusal":
                    raise Refusal(getattr(c, "refusal", "refused"))
        parsed = resp.output_parsed
        u = resp.usage
        in_tok, out_tok = getattr(u, "input_tokens", 0), getattr(u, "output_tokens", 0)
        rec = CallRecord(role=role, provider=self.provider, model=self.model, model_version=resp.model,
                         input_tokens=in_tok, output_tokens=out_tok,
                         cost_usd=price_call(self.pricing, self.price_key, in_tok, out_tok),
                         elapsed_ms=(time.perf_counter() - t0) * 1000)
        return (parsed.model_dump() if parsed else {}), rec

    def select(self, obs):
        return self._call("selector", select_prompt(self.domain), self._select_schema, obs)

    def classify(self, obs):
        return self._call("classifier", classify_prompt(self.domain), self._classify_schema, obs)  # no probabilities


PROVIDERS = {
    "mock": "Offline rules from the domain (free, deterministic). Validates mechanics, not model quality.",
    "openai": "OpenAI Decisions API (needs OPENAI_API_KEY). Returns probabilities.",
    "openai-responses": "OpenAI Responses API structured output (needs OPENAI_API_KEY). No probabilities.",
}


def make_adapter(name: str, cfg: AppConfig, pricing: dict, domain: Domain, **kw):
    if name == "mock":
        return MockAdapter(cfg, pricing, domain, **kw)
    if name == "openai":
        return OpenAIDecisionsAdapter(cfg, pricing, domain)
    if name == "openai-responses":
        return OpenAIResponsesAdapter(cfg, pricing, domain)
    raise ValueError(f"unknown provider {name!r}; choose from {list(PROVIDERS)}")


def describe_provider(name: str, cfg: AppConfig) -> str:
    """Short label for who makes the decisions (recorded on every run and export)."""
    if name == "mock":
        return f"Mock rules, no AI ({cfg.provider.mock_model})"
    if name == "openai":
        return f"OpenAI Decisions API · {os.environ.get('YANTRAA_DECISIONS_MODEL', cfg.provider.decisions_model)}"
    if name == "openai-responses":
        return f"OpenAI Responses API · {os.environ.get('YANTRAA_OPENAI_MODEL', cfg.provider.openai_model)}"
    return name
