"""Deterministic clock primitives for initiative contract tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .contracts import TimingValidationError, require_timezone_aware


class ClockError(ValueError):
    """Raised when a fake clock receives an invalid time transition."""


@dataclass
class FakeClock:
    """A manually advanced clock that never waits for wall-clock time."""

    _current: datetime

    def __post_init__(self) -> None:
        try:
            require_timezone_aware(self._current, field="current")
        except TimingValidationError as exc:
            raise ClockError(str(exc)) from exc

    def now(self) -> datetime:
        return self._current

    def advance_to(self, target: datetime) -> datetime:
        try:
            require_timezone_aware(target, field="target")
        except TimingValidationError as exc:
            raise ClockError(str(exc)) from exc
        if target < self._current:
            raise ClockError("fake clock cannot move backwards")
        self._current = target
        return self._current

    def advance_by(self, delta: timedelta) -> datetime:
        if not isinstance(delta, timedelta):
            raise ClockError("delta must be a datetime.timedelta")
        if delta < timedelta(0):
            raise ClockError("fake clock cannot move backwards")
        return self.advance_to(self._current + delta)


__all__ = ["ClockError", "FakeClock"]
