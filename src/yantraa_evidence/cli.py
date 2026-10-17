"""`yantraa` command line: overview, experiment, evaluate. Calls the same API as `import yantraa_evidence`."""

from __future__ import annotations

import argparse
import json
import sys

from . import datasets, logtracker
from .adapters import PROVIDERS
from .config import load_config


def _fmt(v):
    return f"{v:.4f}" if isinstance(v, float) else ("unknown" if v is None else v)


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=None, help="path to a YAML config (default: config/default.yaml)")
    common.add_argument("--domain", default=None, help="registered name, 'module:ATTR' or 'path/file.py:ATTR'")
    p = argparse.ArgumentParser(prog="yantraa", description="Selective evidence retrieval research toolkit")
    sub = p.add_subparsers(dest="cmd", required=True)

    ov = sub.add_parser("overview", parents=[common],
                        help="what is available: domain, strategies, decision-makers, data, results")
    ov.add_argument("--json", action="store_true")
    ov.add_argument("--problems", type=int, default=0, metavar="N", help="also print the last N logged problems")

    ex = sub.add_parser("experiment", parents=[common], help="design and run an experiment (or one case)")
    ex.add_argument("--split", default="dev")
    ex.add_argument("--strategies", default=None, help="comma-separated (default: all built-in)")
    ex.add_argument("--provider", default="mock", choices=list(PROVIDERS))
    ex.add_argument("--limit", type=int, default=None, help="first N cases only (smoke runs)")
    ex.add_argument("--trials", type=int, default=1)
    ex.add_argument("--estimate-only", action="store_true", help="print the worst-case spend and stop")
    ex.add_argument("--case", default=None, help="run one case (index or case_id) and print its trace")
    ex.add_argument("--generate", action="store_true", help="(re)create the domain's synthetic cases and stop")
    ex.add_argument("--seed", type=int, default=None)

    ev = sub.add_parser("evaluate", parents=[common],
                        help="report a saved experiment or compare it against a baseline")
    ev.add_argument("batch_id", nargs="?", help="saved experiment (default: the latest)")
    ev.add_argument("--reference", default=None, help="baseline strategy (default: fetch_all)")
    ev.add_argument("--against", default=None, metavar="BATCH_ID", help="compare with an earlier experiment")
    ev.add_argument("--list", action="store_true", help="list saved experiments")
    ev.add_argument("--json", action="store_true")
    a = p.parse_args(argv)

    cfg = load_config(a.config)
    logtracker.setup(cfg.path(cfg.log_path))
    try:
        if a.cmd == "overview":
            from .overview import overview, to_text

            o = overview(cfg, a.domain)
            print(json.dumps(o, indent=2, default=str) if a.json else to_text(o))
            for row in logtracker.read(cfg.path(cfg.log_path), "WARNING", a.problems) if a.problems else []:
                print(json.dumps(row))
        elif a.cmd == "experiment":
            return _experiment(a, cfg)
        elif a.cmd == "evaluate":
            return _evaluate(a, cfg)
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        logtracker.track("cli_error", 40, cmd=a.cmd, detail=str(e))
        return 2
    except Exception as e:
        logtracker.track("cli_crash", 40, exc=True, cmd=a.cmd)
        print(f"error: {type(e).__name__}: {e} (details in {cfg.log_path})", file=sys.stderr)
        return 1
    return 0


def _experiment(a, cfg) -> int:
    from .experiment import Experiment
    from .strategies import BUILT_IN

    if a.seed is not None:
        cfg.seed = a.seed
    strategies = [s.strip() for s in a.strategies.split(",") if s.strip()] if a.strategies else list(BUILT_IN)
    exp = Experiment(domain=a.domain, split=a.split, strategies=strategies, provider=a.provider, limit=a.limit,
                     trials=a.trials, config=cfg)
    if a.generate:
        print(json.dumps(datasets.generate(exp.cfg, exp.dom), indent=2))
        return 0
    if a.case is not None:
        r = exp.run_case(a.case, strategies[0])
        for s in r.steps:
            print(f"[{s.index}] {s.kind:8} {s.action:15} {s.status:14} {s.summary}")
        print(f"Decision-maker: {r.provider_label} (reported version: {r.model_version or 'n/a'})")
        print(f"=> {r.terminal.action} ({r.stop_reason}); answer={r.oracle_action}; cost={_fmt(r.costs.total)}; "
              f"run_id={r.run_id}")
        return 0
    print("Domain:", exp.dom.name, "| split:", a.split, "| decision-maker:", a.provider)
    print("Spend estimate:", json.dumps(exp.estimate()))
    if a.estimate_only:
        return 0
    res = exp.run()
    print(res.report().to_text())
    print(f"\nSaved as {res.batch_id}. Exported to {res.export_dir}")
    return 0


def _evaluate(a, cfg) -> int:
    from .evaluate import compare_to_baseline, evaluate, saved_experiments

    if a.list:
        for b in saved_experiments(cfg):
            print(b["batch_id"], b["created_at"], b["domain"], b["provider"], b["split"], ",".join(b["strategies"]))
        return 0
    batch = a.batch_id
    if batch is None:
        saved = saved_experiments(cfg)
        if not saved:
            raise KeyError("no saved experiments yet; run `yantraa experiment` first")
        batch = saved[0]["batch_id"]
    if a.against:
        rows = compare_to_baseline(batch, a.against, cfg)
        if a.json:
            print(json.dumps(rows, indent=2))
            return 0
        print(f"{batch} minus {a.against} (paired by case; negative = lower):")
        for c in rows:
            ci = c["ci95"] and [round(x, 4) for x in c["ci95"]]
            print(f"  {c['strategy']:<22} {c['metric']:<10} {_fmt(c['mean_diff'])}  CI95 {ci}  n={c['n_cases']}")
        return 0
    report = evaluate(batch, cfg, reference=a.reference, domain=a.domain)
    print(json.dumps(report.to_dict(), indent=2, default=str) if a.json else f"Experiment {batch}\n\n" +
          report.to_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
