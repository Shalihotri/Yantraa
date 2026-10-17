import json

import pytest

from yantraa_evidence.adapters import MockAdapter
from yantraa_evidence.config import for_domain, load_config, price_call
from yantraa_evidence.domain import get_domain
from yantraa_evidence.domains.returns import SCENARIOS, assess_return, select_policy
from yantraa_evidence.evaluate import decision_loss, metrics, paired_bootstrap
from yantraa_evidence.runner import Session, StopRun, run_case
from yantraa_evidence.storage import Store
from yantraa_evidence.strategies import BUILT_IN, STRATEGIES
from yantraa_evidence.tools import FixtureToolbox, ToolError

R = get_domain("returns")


@pytest.fixture(scope="module")
def cfg(tmp_path_factory):
    c = for_domain(load_config(), R)
    tmp = tmp_path_factory.mktemp("y")
    c.db_path, c.log_path, c.exports_dir = str(tmp / "t.db"), str(tmp / "log.jsonl"), str(tmp / "exp")
    return c


@pytest.fixture(scope="module")
def cases():
    return R.generate(42)


@pytest.fixture(scope="module")
def pricing():
    return {"version": "t", "models": {"mock-rules-1": {"input_per_mtok": 0.4, "output_per_mtok": 1.6}}}


def family(cases, name, split="dev", pred=lambda c: True):
    return next(c for c in cases[split] if c.scenario == name and pred(c))


def run(case, strategy, cfg, pricing, **kw):
    return run_case(case, strategy, cfg, adapter=MockAdapter(cfg, pricing, R, **kw), pricing=pricing)


# ---------------------------------------------------------------- dataset
def test_generator_is_seeded_and_split_by_template(cases):
    assert len(cases["dev"]) == len(cases["test"]) == 120
    assert R.generate(42)["dev"][0] == cases["dev"][0]
    dev_t = {c.template_id for c in cases["dev"]}
    test_t = {c.template_id for c in cases["test"]}
    assert not dev_t & test_t
    assert set(SCENARIOS) == {c.scenario for c in cases["test"]}
    for split in cases.values():
        assert {c.oracle_action for c in split} == {"approve", "reject", "escalate"}


# ---------------------------------------------------------------- isolation
def test_observation_hides_labels_and_unfetched_evidence(cases, cfg, pricing):
    case = family(cases, "clean_approve")
    s = Session(case, cfg, MockAdapter(cfg, pricing, R), pricing, "run_x", R)
    s.fetch("get_order")
    blob = s.observation().model_dump_json()
    assert case.case_id not in blob and case.scenario not in blob and "oracle" not in blob
    assert "damage_status" not in blob and "return_window_days" not in blob  # unfetched sources
    assert "purchase_age_days" in blob  # fetched source is visible
    insp = case.hidden_evidence["get_inspection"].records[0].record_id
    assert insp not in blob


# ---------------------------------------------------------------- tools
def test_source_specific_fetch_and_repeat_rejected(cases, cfg):
    case = family(cases, "clean_approve")
    tb = FixtureToolbox(case, cfg, R, "cr_1")
    res = tb.fetch("get_inspection")
    assert res.status == "ok" and {e.source_id for e in res.evidence} == {"get_inspection"}
    assert set(res.evidence[0].payload) == {"damage_status", "inspector"}
    with pytest.raises(ToolError) as e:
        tb.fetch("get_inspection")
    assert e.value.code == "repeated_fetch"


def test_unavailable_evidence_is_typed_not_invented(cases, cfg, pricing):
    case = family(cases, "unavailable_tool", pred=lambda c: not c.hidden_evidence["get_policy"].available)
    res = FixtureToolbox(case, cfg, R, "cr").fetch("get_policy")
    assert res.status == "unavailable" and res.evidence == []
    r = run(case, "selective", cfg, pricing)
    assert r.terminal.action == "escalate" and r.fetch_count == 1  # selective stops: nothing can resolve


def test_cross_item_link_rejected(cases, cfg):
    case = family(cases, "missing_evidence")
    foreign = case.hidden_evidence["get_inspection"].records[0].model_copy(update={"subject_id": "it_other"})
    case = case.model_copy(deep=True)
    case.hidden_evidence["get_inspection"].records = [foreign]
    case.hidden_evidence["get_inspection"].available = True
    res = FixtureToolbox(case, cfg, R, "cr").fetch("get_inspection")
    assert res.status == "link_rejected" and res.evidence == [] and res.rejected_records
    other_case = foreign.model_copy(update={"subject_id": case.subject_id, "case_id": "c_else"})
    case.hidden_evidence["get_inspection"].records = [other_case]
    assert FixtureToolbox(case, cfg, R, "cr").fetch("get_inspection").status == "link_rejected"
    assert R.oracle(case) == "escalate"


def test_policy_version_matching_by_date(cases):
    case = family(cases, "clean_approve")
    recs = case.hidden_evidence["get_policy"].records
    cat = case.initial_facts["category"]
    assert select_policy(recs, "2026-02-28", cat).version == "RP-2025"
    assert select_policy(recs, "2026-03-01", cat).version == "RP-2026"
    assert select_policy(recs, "2026-03-01", "nonexistent") is None


def test_policy_boundary_inclusive(cases):
    for c in [c for c in cases["dev"] if c.scenario == "policy_boundary"]:
        order = c.hidden_evidence["get_order"].records[0].payload
        recs = c.hidden_evidence["get_policy"].records
        pol = select_policy(recs, order["purchase_date"], c.initial_facts["category"])
        on_boundary = order["purchase_age_days"] == pol.payload["return_window_days"]
        assert c.oracle_action == ("approve" if on_boundary else "reject")


def test_contradictory_records_preserved(cases, cfg, pricing):
    case = family(cases, "missing_evidence",
                  pred=lambda c: len(c.hidden_evidence["get_inspection"].records) == 2)
    r = run(case, "fetch_all", cfg, pricing)
    insp = [n for n in r.graph["nodes"] if n["kind"] == "Evidence" and n["data"]["source_id"] == "get_inspection"]
    assert {n["data"]["payload"]["damage_status"] for n in insp} == {"confirmed_damaged", "no_damage"}
    assert r.terminal.action == "escalate" and r.terminal.reason_code == "conflicting_evidence"


# ---------------------------------------------------------------- answer key & costs
def test_answer_key_known_answers():
    pol = {"return_window_days": 30, "requires_delivery": True, "requires_damage": True}
    order = {"order_status": "delivered", "purchase_age_days": 30}
    dmg = [{"damage_status": "confirmed_damaged"}]
    assert assess_return(order, pol, dmg).action == "approve"
    assert assess_return({**order, "purchase_age_days": 31}, pol, dmg).action == "reject"
    assert assess_return({**order, "order_status": "shipped"}, pol, None).action == "reject"
    assert assess_return(order, pol, [{"damage_status": "inconclusive"}]).action == "escalate"
    assert assess_return(order, None, dmg).action == "escalate"
    assert assess_return(None, pol, [{"damage_status": "no_damage"}]).action == "reject"


def test_decision_loss_and_pricing(cfg):
    L = cfg.loss
    assert decision_loss("approve", "reject", L) == 20
    assert decision_loss("reject", "approve", L) == 5
    assert decision_loss("escalate", "approve", L) == 1
    assert decision_loss("escalate", "escalate", L) == 0
    assert price_call({"models": {"m": {"input_per_mtok": 1.0, "output_per_mtok": 2.0}}}, "m", 1e6, 1e6) == 3.0
    assert price_call({"models": {"m": {"input_per_mtok": None, "output_per_mtok": 2.0}}}, "m", 1, 1) is None
    assert price_call({"models": {}}, "missing", 1, 1) is None


def test_unknown_price_propagates_to_unknown_total(cases, cfg):
    r = run(family(cases, "clean_approve"), "initial_only", cfg, {"models": {}})
    assert r.costs.model is None and r.costs.total is None


def test_five_strategies_known_answers(cases, cfg, pricing):
    case = family(cases, "clean_approve")
    expect = {"initial_only": (0, "escalate"), "fetch_all": (3, "approve"), "fixed_order": (3, "approve"),
              "confidence_threshold": (3, "approve"), "selective": (3, "approve")}
    for name, (n, action) in expect.items():
        r = run(case, name, cfg, pricing)
        assert (r.fetch_count, r.terminal.action) == (n, action), name
        expected_retrieval = sum(cfg.sources[t].cost for t in ("get_order", "get_policy", "get_inspection")[:n])
        assert r.costs.retrieval == pytest.approx(expected_retrieval)
        assert r.costs.total == pytest.approx(r.costs.retrieval + r.costs.model + r.costs.decision_loss)
    reject = family(cases, "not_delivered")
    assert run(reject, "fixed_order", cfg, pricing).fetch_count == 2  # order+policy suffice
    sel = run(reject, "selective", cfg, pricing)
    assert sel.fetch_count == 2 and sel.terminal.action == "reject"
    assert [s.action for s in sel.steps if s.kind == "fetch"] == ["get_policy", "get_order"]


def test_confidence_threshold_unavailable_without_probabilities(cases, cfg, pricing):
    class NoProbs(MockAdapter):
        def classify(self, obs):
            out, rec = super().classify(obs)
            out.pop("probabilities")
            return out, rec

    r = run_case(family(cases, "clean_approve"), "confidence_threshold", cfg, adapter=NoProbs(cfg, pricing, R),
                 pricing=pricing)
    assert r.status == "unavailable" and r.stop_reason == "probabilities_unavailable"
    assert metrics([r])["n"] == 0


# ---------------------------------------------------------------- loop guards
@pytest.mark.parametrize("mode,reason", [("error", "provider_error"), ("refusal", "refusal"),
                                         ("malformed", "invalid_output"), ("illegal", "illegal_action")])
def test_failures_escalate_with_reason(cases, cfg, pricing, mode, reason):
    from yantraa_evidence import logtracker

    logtracker.setup(cfg.path(cfg.log_path))
    r = run(family(cases, "clean_approve"), "selective", cfg, pricing, fail_mode=mode)
    assert r.stop_reason == reason and r.terminal.action == "escalate"
    if mode == "illegal":  # mock selector always asks for get_order, so the 2nd request is illegal
        assert r.fetch_count == 1
    logged = logtracker.read(cfg.path(cfg.log_path), "WARNING", 5)
    assert any(x["event"] == "run_escalated_by_failure" and x["stop_reason"] == reason for x in logged)


def test_budget_limits_checked_before_calls(cases, cfg, pricing):
    case = family(cases, "clean_approve")
    tight = cfg.model_copy(deep=True)
    tight.limits.max_classifier_calls = 1
    r = run_case(case, "fixed_order", tight, adapter=MockAdapter(tight, pricing, R), pricing=pricing)
    assert r.stop_reason == "budget_classifier" and r.terminal.action == "escalate"
    assert sum(s.kind == "classify" for s in r.steps) == 1
    tight.limits.max_classifier_calls, tight.limits.spend_cap_usd = 4, 0.015
    r = run_case(case, "fetch_all", tight, adapter=MockAdapter(tight, pricing, R), pricing=pricing)
    assert r.stop_reason == "budget_spend" and r.fetch_count == 1
    tight.limits.spend_cap_usd, tight.limits.max_seconds = 1.0, 0.0
    r = run_case(case, "fetch_all", tight, adapter=MockAdapter(tight, pricing, R), pricing=pricing)
    assert r.stop_reason == "budget_time" and r.fetch_count == 0


def test_fetch_limit(cases, cfg, pricing):
    tight = cfg.model_copy(deep=True)
    tight.limits.max_fetches = 2
    s = Session(family(cases, "clean_approve"), tight, MockAdapter(tight, pricing, R), pricing, "r", R)
    s.fetch("get_order")
    s.fetch("get_policy")
    assert s.legal_actions() == ["stop"]
    with pytest.raises(StopRun) as e:
        s.fetch("get_inspection")
    assert e.value.reason == "budget_fetches"


def test_live_adapter_without_key_escalates(cases, cfg, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = run_case(family(cases, "clean_approve"), "selective", cfg, provider="openai")
    assert r.stop_reason == "provider_error" and r.terminal.action == "escalate"


# ---------------------------------------------------------------- graph & storage
def test_graph_export_reload_equivalence(cases, cfg, pricing):
    r = run(family(cases, "clean_approve"), "fetch_all", cfg, pricing)
    kinds = {n["kind"] for n in r.graph["nodes"]}
    assert kinds == {"Case", "Item", "Order", "PolicyVersion", "Inspection", "Evidence", "Decision"}
    rels = {l["rel"] for l in r.graph["links"]}
    assert {"concerns", "contains", "applies_to", "checks", "supports"} <= rels
    assert all("run_id" in l and "created_at" in l for l in r.graph["links"] if l["dst"].startswith("dec_"))
    store = Store(cfg.path(cfg.db_path))
    store.save_runs([r])
    back = store.load_run(r.run_id)
    assert back.graph == r.graph
    assert json.loads(back.model_dump_json()) == json.loads(r.model_dump_json())


def test_graph_only_fetched_portion(cases, cfg, pricing):
    r = run(family(cases, "not_delivered"), "selective", cfg, pricing)
    assert "Inspection" not in {n["kind"] for n in r.graph["nodes"]}


def test_bootstrap_paired_and_seeded(cases, cfg, pricing):
    sub = cases["dev"][:20]
    a = [run(c, "selective", cfg, pricing) for c in sub]
    b = [run(c, "fetch_all", cfg, pricing) for c in sub]
    r1 = paired_bootstrap(a, b, lambda r: r.costs.total, 500, 1)
    r2 = paired_bootstrap(a, b, lambda r: r.costs.total, 500, 1)
    assert r1 == r2 and r1["n_cases"] == 20 and r1["ci95"][0] <= r1["mean_diff"] <= r1["ci95"][1]


def test_all_strategies_registered():
    assert set(BUILT_IN) == {"initial_only", "fetch_all", "fixed_order", "confidence_threshold", "selective"}
    assert set(BUILT_IN) <= set(STRATEGIES)


def test_bundled_defaults_match_config_dir():
    from pathlib import Path

    import yantraa_evidence

    pkg = Path(yantraa_evidence.__file__).parent / "defaults"
    for name in ("default.yaml", "pricing.yaml"):
        assert (pkg / name).read_text() == (Path(__file__).parents[1] / "config" / name).read_text(), name


def test_dotenv_loads_without_overriding(tmp_path, monkeypatch):
    import os

    from yantraa_evidence.config import load_dotenv

    env = tmp_path / ".env"
    env.write_text('# c\nYT_A="one"\nexport YT_B=two\nYT_C=env\n', encoding="utf-8")
    monkeypatch.setenv("YT_C", "shell")
    monkeypatch.delenv("YT_A", raising=False)
    monkeypatch.delenv("YT_B", raising=False)
    assert sorted(load_dotenv(env)) == ["YT_A", "YT_B"]
    assert (os.environ["YT_A"], os.environ["YT_B"], os.environ["YT_C"]) == ("one", "two", "shell")


def test_logs_redact_api_keys(tmp_path):
    from yantraa_evidence import logtracker

    logtracker.setup(tmp_path / "log.jsonl")
    fake_key = "sk-" + "proj-" + "AbCdEfGh" + "IjKlMnOp1234"  # built at runtime so secret scanners stay quiet
    msg = f"Incorrect API key provided: {fake_key}. Bearer tok_123456"
    logtracker.track("provider_failed", 30, detail=msg)
    text = (tmp_path / "log.jsonl").read_text(encoding="utf-8")
    assert "AbCdEfGh" not in text and "tok_123456" not in text and "sk-proj***" in text
