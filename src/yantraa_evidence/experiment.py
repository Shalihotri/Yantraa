"""Experiment: design and run a comparison of evidence-gathering strategies.

    from yantraa_evidence import Experiment

    exp = Experiment(domain="returns", split="dev", strategies=["selective", "fetch_all"],
                     provider="mock", limit=40, overrides={"loss": {"approve": 50}})
    print(exp.estimate())          # worst-case spend before anything runs
    result = exp.run()             # scored, saved to SQLite and exported (CSV, JSONL, JSON)
    one = exp.run_case(0, "selective")   # a single traced decision

Every run records its config hash, seed, generator and prompt versions, model version
and step-by-step trace, so results are reproducible and comparable later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import datasets, logtracker
from .config import AppConfig, apply_overrides, for_domain, load_config
from .domain import Domain, get_domain
from .runner import estimate_spend, run_batch, run_case
from .schemas import Case, RunResult
from .strategies import BUILT_IN, STRATEGIES


@dataclass
class ExperimentResult:
    batch_id: str
    domain: str
    split: str
    provider: str
    strategies: list[str]
    runs: list[RunResult]
    summary: dict
    export_dir: str | None = None

    def report(self, reference: str | None = None):
        from .evaluate import evaluate

        return evaluate(self, reference=reference)


@dataclass
class Experiment:
    """A reproducible experiment design. Every field has a sensible default."""

    domain: str | Domain | None = None  # registered name, 'module:ATTR', 'file.py:ATTR' or a Domain
    split: str = "dev"
    strategies: list[str] = field(default_factory=lambda: list(BUILT_IN))
    provider: str = "mock"  # "mock" (offline), "openai", "openai-responses"
    limit: int | None = None  # first N cases only (smoke runs)
    trials: int = 1
    cases: list[Case] | None = None  # bring your own cases instead of reading case files
    overrides: dict | None = None  # {"costs": {...}, "loss": {...}, "limits": {...}, "confidence_threshold": x}
    config: AppConfig | str | Path | None = None  # AppConfig or path to a YAML config
    adapter_factory: Callable | None = None  # custom decision-maker: () -> object with select/classify
    save: bool = True  # persist to SQLite and write exports

    def __post_init__(self):
        base = self.config if isinstance(self.config, AppConfig) else load_config(self.config)
        self.dom = get_domain(self.domain or base.domain)
        self.cfg = for_domain(apply_overrides(base, self.overrides), self.dom)
        logtracker.setup(self.cfg.path(self.cfg.log_path))
        unknown = [s for s in self.strategies if s not in STRATEGIES]
        if unknown:
            raise ValueError(f"unknown strategies {unknown}; registered: {sorted(STRATEGIES)}")

    # ---------------------------------------------------------- data
    def load_cases(self) -> list[Case]:
        """The cases this experiment will use (generating synthetic ones on first use if possible)."""
        if self.cases is not None:
            return self.cases[: self.limit]
        folder = datasets.data_dir(self.cfg, self.dom)
        if not (folder / f"{self.split}.jsonl").exists():
            try:
                datasets.generate(self.cfg, self.dom)
            except NotImplementedError:
                pass  # load_cases below reports the missing file
        return datasets.load_cases(folder, self.split)[: self.limit]

    def _case(self, ref: int | str | Case) -> Case:
        if isinstance(ref, Case):
            return ref
        cases = self.load_cases()
        if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
            return cases[int(ref)]
        found = next((c for c in cases if c.case_id == ref), None)
        if found is None:
            raise KeyError(f"no case {ref!r} in split {self.split!r}")
        return found

    # ---------------------------------------------------------- run
    def estimate(self) -> dict:
        """Worst-case model calls and spend for this design. Not a billing guarantee."""
        n = len(self.load_cases()) * self.trials
        return estimate_spend(n, self.strategies, self.cfg, self.provider, self.dom)

    def run_case(self, case: int | str | Case, strategy: str = "selective") -> RunResult:
        """One traced decision (by index, case ID or Case). Saved as a single run when save=True."""
        r = run_case(self._case(case), strategy, self.cfg, self.provider, self.dom,
                     adapter=self.adapter_factory() if self.adapter_factory else None)
        if self.save:
            from .storage import Store

            Store(self.cfg.path(self.cfg.db_path)).save_runs([r])
        return r

    def run(self, progress: Callable[[float], None] | None = None) -> ExperimentResult:
        """Run every strategy on every case, score, compare against the reference and persist."""
        from .adapters import describe_provider
        from .evaluate import evaluate
        from .storage import Store, export_batch

        cases = self.load_cases()
        batch_id, runs = run_batch(cases, self.strategies, self.cfg, self.provider, self.dom, self.trials, progress,
                                   self.adapter_factory)
        report = evaluate(runs, self.cfg, domain=self.dom)
        summary = {"batch_id": batch_id, "domain": self.dom.name, "split": self.split, "provider": self.provider,
                   "decision_maker": describe_provider(self.provider, self.cfg), "strategies": self.strategies,
                   "trials": self.trials, "n_cases": len(cases), "config_hash": self.cfg.hash(),
                   "generator_version": next((c.generator_version for c in cases if c.generator_version), None),
                   "prompt_version": self.cfg.prompt_version, "seed": self.cfg.seed, **report.to_dict()}
        export = None
        if self.save:
            store = Store(self.cfg.path(self.cfg.db_path))
            store.save_runs(runs)
            store.save_batch(batch_id, self.provider, self.split, self.strategies, self.cfg.model_dump(mode="json"),
                             summary)
            export = str(export_batch(self.cfg.path(self.cfg.exports_dir) / batch_id, runs, report.metrics, summary))
        return ExperimentResult(batch_id, self.dom.name, self.split, self.provider, self.strategies, runs, summary,
                                export)
