"""Public API (overview -> experiment -> evaluate), custom domains and strategies, and the CLI. Offline."""

from pathlib import Path

import pytest

from yantraa_evidence import (
    Domain,
    Experiment,
    Source,
    compare_to_baseline,
    evaluate,
    get_domain,
    overview,
    register_strategy,
)
from yantraa_evidence.adapters import MockAdapter
from yantraa_evidence.config import for_domain, load_config
from yantraa_evidence.strategies import STRATEGIES

EXAMPLE = str(Path(__file__).parents[1] / "examples" / "insurance_claims.py") + ":DOMAIN"


@pytest.fixture
def cfg(tmp_path):
    c = load_config()
    c.data_dir, c.db_path = str(tmp_path / "data"), str(tmp_path / "runs" / "t.db")
    c.exports_dir, c.log_path = str(tmp_path / "runs" / "exp"), str(tmp_path / "log.jsonl")
    return c


def test_overview_describes_domain_strategies_and_data(cfg):
    o = overview(cfg)
    assert o["domain"]["name"] == "returns" and o["domain"]["fallback"] == "escalate"
    assert {"selective", "fetch_all"} <= set(o["strategies"]) and "mock" in o["providers"]
    assert o["settings"]["source_costs"]["get_inspection"] == pytest.approx(0.10)
    assert o["data"]["splits"] == {}  # nothing generated yet in a fresh folder


def test_experiment_runs_saves_and_evaluates(cfg):
    exp = Experiment(split="dev", limit=12, strategies=["selective", "fetch_all", "initial_only"], config=cfg)
    assert exp.estimate()["max_model_calls"] == 12 * (5 + 1 + 1)
    res = exp.run()  # generates synthetic data on first use
    assert len(res.runs) == 36 and Path(res.export_dir, "metrics.csv").exists()
    report = evaluate(res.batch_id, cfg)  # reloaded from SQLite
    assert report.reference == "fetch_all" and report.n_cases == 12
    assert {c["strategy"] for c in report.paired_comparisons} == {"selective", "initial_only"}
    assert all("wrong_approve" in m and "fallback_rate" in m for m in report.metrics)
    assert "initial_only" in report.accuracy_by_scenario and report.mistakes
    assert "Caveats" in report.to_text()
    again = Experiment(split="dev", limit=12, strategies=["selective"], config=cfg).run()
    diff = compare_to_baseline(again, res, cfg)
    assert {(d["strategy"], d["metric"]) for d in diff} == {("selective", "total_cost"), ("selective", "error")}
    assert all(abs(d["mean_diff"]) < 1e-4 for d in diff)  # mock rules are deterministic


def test_overrides_change_costs_and_penalties(cfg):
    exp = Experiment(limit=3, strategies=["initial_only"], config=cfg, save=False,
                     overrides={"costs": {"get_inspection": 1.0}, "loss": {"escalate": 7}})
    assert exp.cfg.sources["get_inspection"].cost == 1.0 and exp.cfg.loss["escalate"] == 7
    r = exp.run_case(0, "initial_only")
    assert r.terminal.action == "escalate" and r.costs.decision_loss in (0, 7)


def test_unknown_names_fail_loudly(cfg):
    with pytest.raises(ValueError, match="not sources or actions"):
        for_domain(cfg.model_copy(update={"loss": {"refund": 3}}), get_domain("returns"))
    with pytest.raises(ValueError, match="unknown strategies"):
        Experiment(strategies=["nope"], config=cfg)
    with pytest.raises(ValueError, match="fallback"):
        type("Bad", (Domain,), {"name": "bad", "sources": (Source("a", "A"),), "actions": {"x": ""}})().validate()


def test_custom_strategy_is_registered_and_runs(cfg):
    @register_strategy(name="policy_only")
    def _policy_only(s):
        """Check only the policy."""
        s.fetch("get_policy")
        return s.classify()

    assert "policy_only" in STRATEGIES
    r = Experiment(limit=1, strategies=["policy_only"], config=cfg, save=False).run_case(0, "policy_only")
    assert r.strategy == "policy_only" and r.fetch_count == 1


def test_invalid_label_from_decision_maker_falls_back(cfg):
    class WrongLabel(MockAdapter):
        def classify(self, obs):
            out, rec = super().classify(obs)
            return out | {"action": "refund"}, rec

    exp = Experiment(limit=1, strategies=["fetch_all"], config=cfg, save=False,
                     adapter_factory=lambda: WrongLabel(exp.cfg, {"models": {}}, exp.dom))
    r = exp.run_case(0, "fetch_all")
    assert r.stop_reason == "invalid_output" and r.terminal.action == "escalate"


def test_custom_domain_from_file_end_to_end(cfg):
    dom = get_domain(EXAMPLE)
    cases = dom.generate(1)
    assert {c.oracle_action for c in cases["dev"]} == {"pay", "deny", "refer"}
    res = Experiment(domain=EXAMPLE, split="test", config=cfg).run()
    rep = evaluate(res, cfg)
    by = {m["strategy"]: m for m in rep.metrics}
    assert by["fetch_all"]["accuracy"] == 1.0  # mock rules + every source = the answer key
    assert by["fetch_all"]["mean_retrievals"] > by["selective"]["mean_retrievals"]
    assert {"wrong_pay", "wrong_deny", "wrong_refer"} <= set(by["selective"])
    kinds = {n["kind"] for n in res.runs[0].graph["nodes"]}
    assert "Claim" in kinds and "Decision" in kinds


def test_cli_overview_experiment_evaluate(cfg, tmp_path, capsys, monkeypatch):
    import yaml

    from yantraa_evidence.cli import main

    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(cfg.model_dump(mode="json")), encoding="utf-8")
    c = ["--config", str(path)]
    assert main(["overview", *c]) == 0
    assert main(["experiment", *c, "--limit", "5", "--strategies", "selective,fetch_all"]) == 0
    assert main(["experiment", *c, "--case", "0", "--strategies", "selective"]) == 0
    assert main(["evaluate", *c]) == 0
    assert main(["evaluate", *c, "--list"]) == 0
    out = capsys.readouterr().out
    assert "Strategies:" in out and "Paired difference vs fetch_all" in out and "=> " in out
    assert main(["evaluate", *c, "b_missing"]) == 2
