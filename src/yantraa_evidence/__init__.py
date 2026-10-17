"""Yantraa Evidence: measure whether checking less evidence makes AI decisions cheaper without making them worse.

Three steps, three modules:

    overview    what is available: domains, strategies, decision-makers, data, settings
    experiment  design and run a comparison (Experiment, run_case, register_strategy)
    evaluate    score it, compare against benchmark baselines and earlier experiments
"""

__version__ = "0.3.0"

from . import domains  # noqa: E402,F401  (registers the built-in domains)
from .domain import Assessment, Domain, Source, get_domain, register_domain  # noqa: E402
from .evaluate import Report, compare_to_baseline, evaluate  # noqa: E402
from .experiment import Experiment, ExperimentResult  # noqa: E402
from .overview import overview  # noqa: E402
from .runner import Session, run_case  # noqa: E402
from .schemas import Case, FixtureSource, RunResult, SourceRecord  # noqa: E402
from .strategies import register_strategy  # noqa: E402

__all__ = [
    "Assessment", "Case", "Domain", "Experiment", "ExperimentResult", "FixtureSource", "Report", "RunResult",
    "Session", "Source", "SourceRecord", "compare_to_baseline", "evaluate", "get_domain", "overview",
    "register_domain", "register_strategy", "run_case",
]
