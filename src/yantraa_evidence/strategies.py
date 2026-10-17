"""Evidence-gathering strategies: the thing an experiment compares.

A strategy is a function that drives a `Session` and returns the final decision:

    s.sources            the domain's source IDs, in checklist order
    s.legal_actions()    unchecked sources still within budget, plus "stop"
    s.fetch(source)      check one source (costs money, counts against limits)
    s.select()           ask the decision-maker which source to check next (or stop)
    s.classify()         ask the shared decision-maker for the final label

Every limit is enforced by the Session, so a strategy cannot overspend. Register your
own with `@register_strategy` and it is available to experiments and the CLI:

    @register_strategy
    def cheapest_first(s):
        for src in sorted(s.sources, key=lambda x: s.cfg.sources[x].cost):
            s.fetch(src)
            d = s.classify()
            if d.action != s.domain.fallback:
                return d
        return d
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from .adapters import ProbabilitiesUnavailable
from .schemas import STOP

if TYPE_CHECKING:
    from .runner import Session
    from .schemas import TerminalDecision

Strategy = Callable[["Session"], "TerminalDecision"]
STRATEGIES: dict[str, Strategy] = {}


def register_strategy(fn: Strategy | None = None, *, name: str | None = None):
    """Decorator (or plain call) that makes a strategy available by name."""

    def add(f: Strategy) -> Strategy:
        STRATEGIES[name or f.__name__] = f
        return f

    return add(fn) if fn is not None else add


def describe(name: str) -> str:
    doc = (STRATEGIES[name].__doc__ or "").strip()
    return doc.splitlines()[0] if doc else ""


@register_strategy
def selective(s: Session):
    """The AI picks which source to check next, one at a time, and when to stop."""
    while True:
        dec = s.select()
        if dec.next_action == STOP:
            break
        s.fetch(dec.next_action)
    return s.classify()


@register_strategy
def fetch_all(s: Session):
    """Check every source, then decide. The reference baseline."""
    for src in s.sources:
        s.fetch(src)
    return s.classify()


@register_strategy
def fixed_order(s: Session):
    """Checklist order; stop as soon as the decision is no longer the fallback."""
    d = None
    for src in s.sources:
        s.fetch(src)
        d = s.classify()
        if d.action != s.domain.fallback:
            break
    return d


@register_strategy
def confidence_threshold(s: Session):
    """Checklist order; stop once the AI's top probability reaches the confidence threshold."""
    d = s.classify()
    for src in s.sources:
        if d.probabilities is None:
            raise ProbabilitiesUnavailable("provider returned no comparable probabilities")
        if max(d.probabilities.values()) >= s.cfg.confidence_threshold:
            break
        s.fetch(src)
        d = s.classify()
    return d


@register_strategy
def initial_only(s: Session):
    """Decide from the request alone, without checking anything. The lower bound."""
    return s.classify()


BUILT_IN = ("selective", "fetch_all", "fixed_order", "confidence_threshold", "initial_only")
