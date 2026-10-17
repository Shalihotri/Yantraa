"""Evaluate: score runs, compare strategies against benchmark baselines, and compare experiments.

    from yantraa_evidence import evaluate
    report = evaluate.evaluate(result)                 # vs the reference baseline (fetch_all)
    print(report.to_text())
    diff = evaluate.compare_to_baseline(new, old)      # e.g. new prompt vs last week's saved run

Caveats encoded here on purpose: penalties are illustrative USD-equivalents unless you
set your own; returned confidence is never treated as calibrated; the simulator
supports comparisons, not causal claims.
"""

from __future__ import annotations

import random
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from .schemas import Case, RunResult

if TYPE_CHECKING:
    from .config import AppConfig
    from .domain import Domain

CAVEATS = [
    "Synthetic data is balanced for debugging; it is not a production distribution.",
    "Mistake penalties are assumptions; check the penalty-sensitivity table before concluding.",
    "Mock runs validate mechanics, not model quality.",
    "Model-reported confidence is not calibrated correctness; no causal claims.",
]


# ------------------------------------------------------------------ scoring
def decision_loss(pred: str, truth: str, loss: dict[str, float]) -> float:
    """Penalty for choosing `pred` when the answer key says `truth` (0 when right)."""
    return 0.0 if pred == truth else float(loss.get(pred, 0.0))


def score(run: RunResult, case: Case, cfg: AppConfig) -> RunResult:
    """Attach the answer key and costs after termination (the decision-maker never saw these)."""
    truth = case.oracle_action
    loss = decision_loss(run.terminal.action, truth, cfg.loss)
    c = run.costs
    total = None if c.model is None else c.retrieval + c.model + loss
    return run.model_copy(update={
        "oracle_action": truth, "correct": run.terminal.action == truth,
        "costs": c.model_copy(update={"decision_loss": loss, "total": total}),
    })


# ------------------------------------------------------------------ metrics
def _pct(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _domain_of(runs: list[RunResult], domain: Domain | None) -> Domain | None:
    if domain is not None or not runs:
        return domain
    from .domain import DOMAINS

    return DOMAINS.get(runs[0].domain)


def metrics(runs: list[RunResult], domain: Domain | None = None) -> dict:
    """Accuracy, mistakes by label, fallback rate, checks, costs and latency for one strategy's runs."""
    done = [r for r in runs if r.status == "completed"]
    n = len(done)
    if not n:
        return {"n": 0, "unavailable": len(runs)}
    domain = _domain_of(runs, domain)
    truth = [r.oracle_action for r in done]
    pred = [r.terminal.action for r in done]
    labels = list(domain.actions) if domain else sorted(set(pred) | set(truth))
    model_costs = [r.costs.model for r in done]
    model_known = all(m is not None for m in model_costs)
    row = {"n": n, "unavailable": len(runs) - n, "accuracy": sum(p == t for p, t in zip(pred, truth)) / n}
    for label in labels:  # wrong_<label>: times this label was chosen when it was not the answer
        row[f"wrong_{label}"] = sum(p == label and t != label for p, t in zip(pred, truth))
    if domain:
        row["fallback_rate"] = pred.count(domain.fallback) / n
    row |= {
        "mean_retrievals": statistics.mean(r.fetch_count for r in done),
        "mean_retrieval_cost": statistics.mean(r.costs.retrieval for r in done),
        "mean_model_cost": statistics.mean(model_costs) if model_known else None,
        "mean_decision_loss": statistics.mean(r.costs.decision_loss for r in done),
        "mean_total_cost": statistics.mean(r.costs.total for r in done) if model_known else None,
        "sim_latency_p50_ms": _pct([r.simulated_latency_ms for r in done], 0.5),
        "sim_latency_p95_ms": _pct([r.simulated_latency_ms for r in done], 0.95),
        "wall_p50_ms": _pct([r.wall_ms for r in done], 0.5),
        "wall_p95_ms": _pct([r.wall_ms for r in done], 0.95),
    }
    return row


def _per_case(runs: list[RunResult], key) -> dict[str, float]:
    """Average repeated trials within a case so bootstrap resamples whole case groups."""
    groups: dict[str, list[float]] = defaultdict(list)
    for r in runs:
        v = key(r)
        if r.status == "completed" and v is not None:
            groups[r.case_id].append(v)
    return {k: statistics.mean(v) for k, v in groups.items()}


def paired_bootstrap(a: list[RunResult], b: list[RunResult], key, samples: int, seed: int) -> dict:
    """Mean(a - b) over shared cases with a seeded percentile 95% interval."""
    pa, pb = _per_case(a, key), _per_case(b, key)
    shared = sorted(set(pa) & set(pb))
    if not shared:
        return {"n_cases": 0, "mean_diff": None, "ci95": None}
    diffs = [pa[c] - pb[c] for c in shared]
    rng = random.Random(seed)
    boots = sorted(statistics.mean(rng.choices(diffs, k=len(diffs))) for _ in range(samples))
    return {"n_cases": len(shared), "mean_diff": statistics.mean(diffs),
            "ci95": [_pct(boots, 0.025), _pct(boots, 0.975)]}


KEYS = {"total_cost": lambda r: r.costs.total, "error": lambda r: float(not r.correct)}


def compare(by_strategy: dict[str, list[RunResult]], cfg: AppConfig, reference: str | None = None) -> list[dict]:
    """Each strategy minus the reference baseline, paired by case, for total cost and error rate."""
    ref = reference or cfg.reference_strategy
    if ref not in by_strategy:
        return []
    rows = []
    for s, runs in by_strategy.items():
        if s == ref:
            continue
        for name, key in KEYS.items():
            boot = paired_bootstrap(runs, by_strategy[ref], key, cfg.bootstrap_samples, cfg.seed)
            rows.append({"strategy": s, "reference": ref, "metric": name, **boot})
    return rows


def sensitivity(runs: list[RunResult], cfg: AppConfig, fallback: str | None = None,
                multipliers=(0.25, 0.5, 1, 2, 4)) -> list[dict]:
    """Recompute mean total cost with mistake penalties scaled (the fallback penalty stays fixed)."""
    rows = []
    for m in multipliers:
        loss = {k: v if k == fallback else v * m for k, v in cfg.loss.items()}
        tot = [r.costs.retrieval + r.costs.model + decision_loss(r.terminal.action, r.oracle_action, loss)
               for r in runs if r.status == "completed" and r.costs.model is not None]
        rows.append({"penalty_multiplier": m, "mean_total_cost": statistics.mean(tot) if tot else None})
    return rows


# ------------------------------------------------------------------ reports
@dataclass
class Report:
    """Everything needed to judge an experiment. `to_dict()` for your app, `to_text()` for a terminal."""

    domain: str
    reference: str
    strategies: list[str]
    n_cases: int
    metrics: list[dict]
    paired_comparisons: list[dict]
    penalty_sensitivity: dict[str, list[dict]]
    accuracy_by_scenario: dict[str, dict[str, float]]
    mistakes: list[dict]
    headline: str
    caveats: list[str] = field(default_factory=lambda: list(CAVEATS))

    def to_dict(self) -> dict:
        return asdict(self)

    def to_text(self) -> str:
        def f(v):
            return "unknown" if v is None else (f"{v:.4f}" if isinstance(v, float) else str(v))

        cols = ["strategy", "n", "accuracy", "fallback_rate", "mean_retrievals", "mean_total_cost", "wall_p50_ms"]
        lines = [self.headline, "", " | ".join(cols)]
        lines += [" | ".join(f(m.get(c)) for c in cols) for m in self.metrics]
        if self.paired_comparisons:
            lines += ["", f"Paired difference vs {self.reference} (negative = lower than the reference):"]
            for c in self.paired_comparisons:
                ci = c["ci95"] and "[" + ", ".join(f"{x:+.4f}" for x in c["ci95"]) + "]"
                diff = "n/a" if c["mean_diff"] is None else f"{c['mean_diff']:+.4f}"
                lines.append(f"  {c['strategy']:<22} {c['metric']:<10} {diff}  CI95 {ci}")
        lines += ["", "Caveats:"] + [f"  - {c}" for c in self.caveats]
        return "\n".join(lines)


def _headline(rows: list[dict], comps: list[dict], ref: str) -> str:
    known = [m for m in rows if m.get("mean_total_cost") is not None]
    if not known:
        return "No strategy has a known total cost (a model price is missing from the pricing file)."
    best = min(known, key=lambda m: m["mean_total_cost"])
    if best["strategy"] == ref:
        return f"The reference baseline '{ref}' had the lowest mean total cost ({best['mean_total_cost']:.4f})."
    c = next((c for c in comps if c["strategy"] == best["strategy"] and c["metric"] == "total_cost"), None)
    text = f"Lowest mean total cost: '{best['strategy']}' ({best['mean_total_cost']:.4f})"
    if c and c["ci95"]:
        lo, hi = c["ci95"]
        verdict = "a clear saving" if hi < 0 else "not a clear difference (the 95% interval includes zero)"
        text += f"; vs '{ref}': {c['mean_diff']:+.4f}, CI95 [{lo:+.4f}, {hi:+.4f}], {verdict}"
    return text + "."


def evaluate(runs, cfg: AppConfig | None = None, reference: str | None = None,
             domain: str | Domain | None = None) -> Report:
    """Report for an ExperimentResult, a list of RunResults, or a saved batch ID."""
    from .config import for_domain, load_config
    from .domain import get_domain

    if isinstance(runs, str):
        runs = load_runs(runs, cfg)
    runs = list(getattr(runs, "runs", runs))
    if not runs:
        raise ValueError("nothing to evaluate: no runs")
    dom = get_domain(domain or runs[0].domain)
    cfg = for_domain(cfg or load_config(), dom)
    by: dict[str, list[RunResult]] = {}
    for r in runs:
        by.setdefault(r.strategy, []).append(r)
    ref = reference or cfg.reference_strategy
    rows = [{"strategy": s, **metrics(rs, dom)} for s, rs in by.items()]
    comps = compare(by, cfg, ref)
    scen: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for r in runs:
        if r.status == "completed":
            scen[r.strategy][r.scenario or "(none)"].append(bool(r.correct))
    by_scenario = {s: {k: sum(v) / len(v) for k, v in sorted(d.items())} for s, d in scen.items()}
    mistakes = [{"strategy": r.strategy, "case_id": r.case_id, "scenario": r.scenario, "decided": r.terminal.action,
                 "answer": r.oracle_action, "checks": r.fetch_count, "stop_reason": r.stop_reason, "run_id": r.run_id}
                for r in runs if r.status == "completed" and not r.correct]
    return Report(domain=dom.name, reference=ref, strategies=list(by), n_cases=len({r.case_id for r in runs}),
                  metrics=rows, paired_comparisons=comps,
                  penalty_sensitivity={s: sensitivity(rs, cfg, dom.fallback) for s, rs in by.items()},
                  accuracy_by_scenario=by_scenario, mistakes=mistakes, headline=_headline(rows, comps, ref))


def compare_to_baseline(candidate, baseline, cfg: AppConfig | None = None) -> list[dict]:
    """Candidate minus a saved benchmark, per strategy, paired by case (e.g. new prompt vs last run).

    Both arguments accept an ExperimentResult, a list of RunResults or a saved batch ID.
    """
    from .config import load_config

    cfg = cfg or load_config()
    cand = load_runs(candidate, cfg) if isinstance(candidate, str) else list(getattr(candidate, "runs", candidate))
    base = load_runs(baseline, cfg) if isinstance(baseline, str) else list(getattr(baseline, "runs", baseline))
    rows = []
    for s in sorted({r.strategy for r in cand} & {r.strategy for r in base}):
        a = [r for r in cand if r.strategy == s]
        b = [r for r in base if r.strategy == s]
        for name, key in KEYS.items():
            rows.append({"strategy": s, "metric": name,
                         **paired_bootstrap(a, b, key, cfg.bootstrap_samples, cfg.seed)})
    return rows


def load_runs(batch_id: str, cfg: AppConfig | None = None) -> list[RunResult]:
    """Runs of a saved experiment (see `yantraa evaluate --list`)."""
    from .config import load_config
    from .storage import Store

    cfg = cfg or load_config()
    runs = Store(cfg.path(cfg.db_path)).runs(batch_id, limit=1_000_000)
    if not runs:
        raise KeyError(f"no saved experiment {batch_id!r}")
    return runs


def saved_experiments(cfg: AppConfig | None = None) -> list[dict]:
    """Saved experiments, newest first: batch_id, created_at, domain, provider, split, strategies."""
    import json

    from .config import load_config
    from .storage import Store

    cfg = cfg or load_config()
    out = []
    for b in Store(cfg.path(cfg.db_path)).batches():
        s = json.loads(b["summary"])
        out.append({"batch_id": b["batch_id"], "created_at": b["created_at"], "domain": s.get("domain"),
                    "provider": b["provider"], "split": b["split"], "strategies": json.loads(b["strategies"])})
    return out
