"""Structured log tracker: every escalation-by-failure, provider error, validation error
and budget exhaustion is written as one JSON line so "what went wrong" can be queried
later (`yantraa overview --problems N`, or `logtracker.read`)."""

from __future__ import annotations

import json
import logging
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path

LOGGER_NAME = "yantraa"
_configured_path: Path | None = None


_SECRET = re.compile(r"(sk-[A-Za-z0-9_\-]{4})[A-Za-z0-9_\-*]{4,}|(Bearer\s+)\S+")


def redact(text: str) -> str:
    """Mask API keys / bearer tokens that provider error messages may echo back."""
    return _SECRET.sub(lambda m: (m.group(1) + "***") if m.group(1) else (m.group(2) + "***"), text)


class _JsonLines(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "event": record.getMessage(),
            **getattr(record, "ctx", {}),
        }
        if record.exc_info:
            entry["exception"] = "".join(traceback.format_exception(*record.exc_info))[-2000:]
        return redact(json.dumps(entry, default=str))


def setup(log_path: str | Path) -> logging.Logger:
    global _configured_path
    path = Path(log_path)
    logger = logging.getLogger(LOGGER_NAME)
    if _configured_path == path:
        return logger
    path.parent.mkdir(parents=True, exist_ok=True)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(_JsonLines())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _configured_path = path
    return logger


def track(event: str, level: int = logging.INFO, exc: bool = False, **ctx) -> None:
    logging.getLogger(LOGGER_NAME).log(level, event, extra={"ctx": ctx}, exc_info=exc)


def read(log_path: str | Path, min_level: str = "WARNING", tail: int = 50) -> list[dict]:
    order = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    path = Path(log_path)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if order.get(row.get("level"), 0) >= order[min_level]:
            rows.append(row)
    return rows[-tail:]
