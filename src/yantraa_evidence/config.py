"""Configuration loading (config/default.yaml + pricing file), domain defaults and stable config hashing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .domain import Domain

_REPO = Path(__file__).resolve().parents[2]
_BUNDLED = Path(__file__).resolve().parent / "defaults"  # copies of config/*.yaml shipped in the wheel


def _root() -> Path:
    """Project root: the current directory if it has config/, else the source checkout (dev installs)."""
    cwd = Path.cwd()
    if (cwd / "config" / "default.yaml").exists() or not (_REPO / "config" / "default.yaml").exists():
        return cwd
    return _REPO


ROOT = _root()
DEFAULT_CONFIG = ROOT / "config" / "default.yaml"


class SourceConfig(BaseModel):
    """Per-source override of a domain default. Unset values keep the domain default."""

    cost: float | None = None
    latency_ms: float | None = None
    available: bool = True  # global switch; per-case availability lives in the case data


class Limits(BaseModel):
    max_fetches: int | None = None  # None = every source of the domain, once
    max_selector_calls: int = 4
    max_classifier_calls: int = 4
    max_seconds: float = 30.0
    spend_cap_usd: float = 0.50


class ProviderConfig(BaseModel):
    mock_model: str = "mock-rules-1"
    mock_latency_ms: float = 250.0
    decisions_model: str = "gpt-6-luna"  # Decisions API (beta)
    openai_model: str = "gpt-6-luna"  # Responses API fallback
    openai_timeout_s: float = 20.0
    est_input_tokens: int = 900
    est_output_tokens: int = 120


class AppConfig(BaseModel):
    domain: str = "returns"
    seed: int = 42
    prompt_version: str = "p2.0"
    data_dir: str = "data"  # cases live in <data_dir>/<domain>/<split>.jsonl
    db_path: str = "runs/experiments.db"
    exports_dir: str = "runs/exports"
    log_path: str = "logs/yantraa.jsonl"
    pricing_file: str = "config/pricing.yaml"
    sources: dict[str, SourceConfig] = Field(default_factory=dict)
    limits: Limits = Field(default_factory=Limits)
    loss: dict[str, float] = Field(default_factory=dict)  # penalty when a label is chosen wrongly
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    confidence_threshold: float = 0.85
    bootstrap_samples: int = 2000
    reference_strategy: str = "fetch_all"

    def path(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else ROOT / p

    def hash(self) -> str:
        blob = json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:12]


def for_domain(cfg: AppConfig, domain: Domain) -> AppConfig:
    """Fill every source cost, latency and mistake penalty from the domain, keeping config overrides.

    Unknown source or label names fail loudly instead of being ignored.
    """
    unknown = sorted(set(cfg.sources) - set(domain.source_ids)) + sorted(set(cfg.loss) - set(domain.actions))
    if unknown:
        raise ValueError(f"config names {unknown} are not sources or actions of domain {domain.name!r}")
    cfg = cfg.model_copy(deep=True)
    cfg.domain = domain.name
    sources = {}
    for s in domain.sources:
        o = cfg.sources.get(s.id, SourceConfig())
        sources[s.id] = SourceConfig(cost=s.cost if o.cost is None else o.cost,
                                     latency_ms=s.latency_ms if o.latency_ms is None else o.latency_ms,
                                     available=o.available)
    cfg.sources = sources
    cfg.loss = {a: float(cfg.loss.get(a, domain.loss.get(a, 0.0))) for a in domain.actions}
    if cfg.limits.max_fetches is None:
        cfg.limits.max_fetches = len(domain.sources)
    return cfg


def load_dotenv(path: Path | None = None) -> list[str]:
    """Load KEY=VALUE lines from the project .env into os.environ (never overrides existing vars).

    Returns the names loaded (never values), so callers can log what came from .env.
    """
    import os

    p = path or ROOT / ".env"
    if not p.exists():
        return []
    loaded = []
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.removeprefix("export ").partition("=")
        key, val = key.strip(), val.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = val
            loaded.append(key)
    return loaded


def load_config(path: str | Path | None = None) -> AppConfig:
    load_dotenv()
    p = Path(path) if path else DEFAULT_CONFIG
    if not path and not p.exists():
        p = _BUNDLED / "default.yaml"
    return AppConfig.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))


def apply_overrides(cfg: AppConfig, o: dict | None) -> AppConfig:
    """Copy of cfg with adjusted source costs, penalties, limits or threshold.

    o = {"costs": {source: usd}, "loss": {label: usd}, "limits": {...}, "confidence_threshold": 0.9}
    """
    cfg = cfg.model_copy(deep=True)
    o = o or {}
    for src, cost in (o.get("costs") or {}).items():
        cfg.sources.setdefault(src, SourceConfig()).cost = float(cost)
    for label, v in (o.get("loss") or {}).items():
        cfg.loss[label] = float(v)
    for k, v in (o.get("limits") or {}).items():
        if not hasattr(cfg.limits, k):
            raise ValueError(f"unknown limit {k!r}")
        setattr(cfg.limits, k, v)
    if o.get("spend_cap_usd") is not None:
        cfg.limits.spend_cap_usd = float(o["spend_cap_usd"])
    if o.get("confidence_threshold") is not None:
        cfg.confidence_threshold = float(o["confidence_threshold"])
    return cfg


def load_pricing(cfg: AppConfig) -> dict:
    """Returns {"version": str, "models": {model: {"input_per_mtok": float|None, ...}}}."""
    p = cfg.path(cfg.pricing_file)
    if not p.exists():
        p = _BUNDLED / Path(cfg.pricing_file).name
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def price_call(pricing: dict, model: str, in_tok: int, out_tok: int) -> float | None:
    """USD cost of one call, or None when the price is missing (unknown, never zero)."""
    p = (pricing.get("models") or {}).get(model)
    if not p or p.get("input_per_mtok") is None or p.get("output_per_mtok") is None:
        return None
    return (in_tok * p["input_per_mtok"] + out_tok * p["output_per_mtok"]) / 1_000_000
