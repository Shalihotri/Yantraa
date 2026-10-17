"""Case files: <data_dir>/<domain>/<split>.jsonl, one `Case` per line, plus manifest.json.

Bring your own data by writing Case objects (with an `oracle_action` answer key) to
these files, or let a domain with a generator create synthetic ones.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from .schemas import Case

if TYPE_CHECKING:
    from .config import AppConfig
    from .domain import Domain


def data_dir(cfg: AppConfig, domain: Domain) -> Path:
    return cfg.path(cfg.data_dir) / domain.name


def write_cases(cases: dict[str, list[Case]], out_dir: Path, seed: int | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    versions = sorted({c.generator_version for rows in cases.values() for c in rows if c.generator_version})
    manifest = {"generator_version": ", ".join(versions) or None, "seed": seed, "splits": {}}
    for split, rows in cases.items():
        (out_dir / f"{split}.jsonl").write_text("".join(c.model_dump_json() + "\n" for c in rows), encoding="utf-8")
        dist: dict[str, int] = {}
        for c in rows:
            dist[c.oracle_action] = dist.get(c.oracle_action, 0) + 1
        manifest["splits"][split] = {"n": len(rows), "answer_distribution": dist}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_cases(path: Path, split: str) -> list[Case]:
    """Cases from <path>/<split>.jsonl (or from `path` itself when it is a .jsonl file)."""
    f = path if path.suffix == ".jsonl" else path / f"{split}.jsonl"
    if not f.exists():
        raise FileNotFoundError(f"{f} not found - run `yantraa experiment --generate` or add your own cases")
    return [Case.model_validate_json(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]


def generate(cfg: AppConfig, domain: Domain, seed: int | None = None) -> dict:
    """(Re)create the domain's synthetic cases and return the manifest."""
    seed = cfg.seed if seed is None else seed
    return write_cases(domain.generate(seed), data_dir(cfg, domain), seed)


def available_splits(cfg: AppConfig, domain: Domain) -> dict[str, int]:
    d = data_dir(cfg, domain)
    if not d.exists():
        return {}
    return {f.stem: sum(1 for line in f.read_text(encoding="utf-8").splitlines() if line.strip())
            for f in sorted(d.glob("*.jsonl"))}
