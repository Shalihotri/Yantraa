"""Decisions API adapter tests with a fake client returning real SDK `Decision` objects (no network)."""

import pytest
from openai.types import Decision

from yantraa_evidence.adapters import MockAdapter, OpenAIDecisionsAdapter, describe_provider
from yantraa_evidence.config import for_domain, load_config
from yantraa_evidence.domain import get_domain
from yantraa_evidence.runner import run_case

R = get_domain("returns")

PRICING = {"models": {"decisions:gpt-6-luna": {"input_per_mtok": 0.10, "output_per_mtok": 0.0}}}


class FakeDecisions:
    """Answers like a well-behaved model by delegating to the mock rules, or misbehaves on demand."""

    def __init__(self, cfg, mode=None):
        self.mock, self.mode, self.calls = MockAdapter(cfg, PRICING, R), mode, []

    def create(self, model, input, questions):
        from yantraa_evidence.schemas import Observation

        self.calls.append(questions)
        if self.mode == "error":
            raise RuntimeError("403 not enabled for this user")
        obs = Observation.model_validate_json(input)
        usage = {"input_tokens": 800, "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 0},
                 "output_tokens": 0, "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 800}
        first = questions[0]
        if self.mode == "refusal":
            answers = [{"type": "refusal", "name": first["name"]}]
        elif first["name"] == "next_action":
            pick = self.mock.select(obs)[0]["next_action"]
            probs = [{"value": c["value"], "probability": 0.9 if c["value"] == pick else 0.1 / (len(
                first["choices"]) - 1 or 1)} for c in first["choices"]]
            answers = [{"type": "choice", "name": "next_action", "choice": pick, "confidence": 0.9,
                        "probabilities": probs}]
        else:
            out = self.mock.classify(obs)[0]
            answers = [{"type": "choice", "name": "action", "choice": out["action"], "confidence": 0.9,
                        "probabilities": [{"value": k, "probability": v} for k, v in out["probabilities"].items()]}]
            answers += [{"type": "predicate", "name": q["name"], "probability": 0.95} for q in questions[1:]]
        return Decision.model_validate({"answers": answers, "model": "gpt-6-luna-2026-10-01", "usage": usage})


class FakeClient:
    def __init__(self, cfg, mode=None):
        self.decisions = FakeDecisions(cfg, mode)


@pytest.fixture(scope="module")
def cfg():
    return for_domain(load_config(), R)


@pytest.fixture(scope="module")
def case():
    return next(c for c in R.generate(42)["dev"] if c.scenario == "clean_approve")


def adapter(cfg, mode=None):
    return OpenAIDecisionsAdapter(cfg, PRICING, R, client=FakeClient(cfg, mode))


def test_selective_end_to_end_records_model_and_cost(cfg, case):
    a = adapter(cfg)
    r = run_case(case, "selective", cfg, provider="openai", adapter=a, pricing=PRICING)
    assert r.terminal.action == "approve" and r.stop_reason == "classifier_decided"
    assert r.model == "gpt-6-luna" and r.model_version == "gpt-6-luna-2026-10-01"
    assert r.provider_label == "OpenAI Decisions API · gpt-6-luna"
    calls = [s.call for s in r.steps if s.call]
    assert all(c.cost_usd == pytest.approx(800 * 0.10 / 1e6) for c in calls)  # input-only billing
    # selector choices are exactly the legal actions at that moment (never an already-fetched source)
    sel_qs = [q[0] for q in a.client.decisions.calls if q[0]["name"] == "next_action"]
    assert [c["value"] for c in sel_qs[1]["choices"]] == ["get_order", "get_inspection", "stop"]
    cls = [s for s in r.steps if s.kind == "classify"][-1]
    assert "delivered 0.95" in cls.summary and cls.call.probabilities["approve"] > 0.9


def test_confidence_threshold_works_with_decisions_probabilities(cfg, case):
    r = run_case(case, "confidence_threshold", cfg, provider="openai", adapter=adapter(cfg), pricing=PRICING)
    assert r.status == "completed" and r.terminal.action == "approve" and r.fetch_count == 3


@pytest.mark.parametrize("mode,reason", [("error", "provider_error"), ("refusal", "refusal")])
def test_decisions_failures_escalate(cfg, case, mode, reason):
    r = run_case(case, "selective", cfg, provider="openai", adapter=adapter(cfg, mode), pricing=PRICING)
    assert r.terminal.action == "escalate" and r.stop_reason == reason


def test_provider_labels(cfg):
    assert describe_provider("openai", cfg) == "OpenAI Decisions API · gpt-6-luna"
    assert describe_provider("openai-responses", cfg) == "OpenAI Responses API · gpt-6-luna"
    assert describe_provider("mock", cfg).startswith("Mock rules, no AI")
