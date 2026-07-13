"""Bounded contracts for the post-dialogue initiative test harness.

This module intentionally contains only data contracts and deterministic
validation.  It does not know about prompts, providers, scheduling, or
outbound message delivery.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Iterable, Literal, Optional


class InitiativeContractError(ValueError):
    """Base exception for invalid initiative-domain data."""


class TimingValidationError(InitiativeContractError):
    """Raised when a timing value is not timezone-aware or well ordered."""


class GoalValidationError(InitiativeContractError):
    """Raised when a plan goal is not part of the bounded contract."""


class ForbiddenGoalError(GoalValidationError):
    """Raised when a recognized but forbidden goal is requested."""


class EvidenceValidationError(InitiativeContractError):
    """Raised when a plan has missing or unknown evidence references."""


@dataclass(frozen=True)
class ValidationIssue:
    """One deterministic validation failure."""

    code: str
    message: str
    field: Optional[str] = None


@dataclass(frozen=True)
class ValidationResult:
    """Small result helper for callers that prefer inspection over exceptions."""

    valid: bool
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return self.valid

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return self.issues

    def raise_for_errors(self) -> None:
        if self.valid:
            return
        message = "; ".join(issue.message for issue in self.issues)
        raise InitiativeContractError(message)


class PlanGoal(str, Enum):
    CHECK_IN = "check_in"
    FOLLOW_UP_TOPIC = "follow_up_topic"
    TOPIC_DISCOVERY = "topic_discovery"
    SILENT = "silent"
    DEMAND_REPLY = "demand_reply"


ALLOWED_PLAN_GOALS = frozenset(
    {
        PlanGoal.CHECK_IN.value,
        PlanGoal.FOLLOW_UP_TOPIC.value,
        PlanGoal.TOPIC_DISCOVERY.value,
        PlanGoal.SILENT.value,
        PlanGoal.DEMAND_REPLY.value,
    }
)
FORBIDDEN_PLAN_GOALS = frozenset({PlanGoal.DEMAND_REPLY.value})


def is_timezone_aware(value: datetime) -> bool:
    """Return whether ``value`` has a usable UTC offset."""

    return value.tzinfo is not None and value.utcoffset() is not None


def require_timezone_aware(value: datetime, *, field: str = "datetime") -> datetime:
    if not isinstance(value, datetime) or not is_timezone_aware(value):
        raise TimingValidationError(f"{field} must be a timezone-aware datetime")
    return value


@dataclass(frozen=True)
class PlanTiming:
    """Relative timing offsets anchored at the planner observation time."""

    observed_at: datetime
    earliest_offset_minutes: int
    preferred_offset_minutes: int
    expires_offset_minutes: int

    def __post_init__(self) -> None:
        require_timezone_aware(self.observed_at, field="observed_at")
        offsets = (
            self.earliest_offset_minutes,
            self.preferred_offset_minutes,
            self.expires_offset_minutes,
        )
        if any(isinstance(offset, bool) or not isinstance(offset, int) for offset in offsets):
            raise TimingValidationError("timing offsets must be integers in minutes")
        if any(offset < 0 for offset in offsets):
            raise TimingValidationError("timing offsets cannot be negative")
        if not (
            self.earliest_offset_minutes
            <= self.preferred_offset_minutes
            <= self.expires_offset_minutes
        ):
            raise TimingValidationError(
                "timing offsets must satisfy earliest <= preferred <= expires"
            )

    @classmethod
    def from_offsets(
        cls,
        observed_at: datetime,
        *,
        earliest: int,
        preferred: int,
        expires: int,
    ) -> "PlanTiming":
        return cls(observed_at, earliest, preferred, expires)

    @property
    def earliest_at(self) -> datetime:
        return self.observed_at + timedelta(minutes=self.earliest_offset_minutes)

    @property
    def preferred_at(self) -> datetime:
        return self.observed_at + timedelta(minutes=self.preferred_offset_minutes)

    @property
    def expires_at(self) -> datetime:
        return self.observed_at + timedelta(minutes=self.expires_offset_minutes)


@dataclass(frozen=True)
class InitiativePlan:
    """Planner output retained by the bounded harness."""

    plan_id: str
    scenario_id: str
    goal: str
    topic_ref: Optional[str] = None
    evidence_refs: tuple[str, ...] = ()
    timing: Optional[PlanTiming] = None
    motive: str = ""
    timing_reason: str = ""
    message_constraints: tuple[str, ...] = ()
    should_initiate: bool = True
    suppressed_reason: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "message_constraints", tuple(self.message_constraints))


# Short alias for workers that refer to the domain object simply as a Plan.
Plan = InitiativePlan


class PlanValidationError(InitiativeContractError):
    """Raised when an InitiativePlan fails deterministic validation."""

    def __init__(self, issues: Iterable[ValidationIssue]):
        self.issues = tuple(issues)
        message = "; ".join(issue.message for issue in self.issues)
        super().__init__(message or "invalid initiative plan")


def _plan_issues(
    plan: InitiativePlan,
    *,
    available_evidence_refs: Optional[Iterable[str]] = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if not isinstance(plan, InitiativePlan):
        return [ValidationIssue("plan_type", "plan must be an InitiativePlan")]
    if not plan.plan_id:
        issues.append(ValidationIssue("missing_plan_id", "plan_id is required", "plan_id"))
    if not plan.scenario_id:
        issues.append(
            ValidationIssue("missing_scenario_id", "scenario_id is required", "scenario_id")
        )

    goal = plan.goal.value if isinstance(plan.goal, PlanGoal) else plan.goal
    if goal not in ALLOWED_PLAN_GOALS:
        issues.append(ValidationIssue("invalid_goal", f"unsupported plan goal: {goal!r}", "goal"))
    elif goal in FORBIDDEN_PLAN_GOALS:
        issues.append(
            ValidationIssue("forbidden_goal", f"plan goal is forbidden: {goal!r}", "goal")
        )

    if not isinstance(plan.should_initiate, bool):
        issues.append(
            ValidationIssue("invalid_should_initiate", "should_initiate must be a boolean")
        )
    if not plan.should_initiate and goal != PlanGoal.SILENT.value:
        issues.append(
            ValidationIssue(
                "non_silent_suppression",
                "a plan that will not initiate must use the silent goal",
                "goal",
            )
        )

    if plan.timing is not None and not isinstance(plan.timing, PlanTiming):
        issues.append(ValidationIssue("invalid_timing", "timing must be a PlanTiming", "timing"))
    elif plan.timing is not None:
        try:
            # Re-run validation here so malformed objects created by unusual
            # deserializers still fail at the contract boundary.
            PlanTiming(
                plan.timing.observed_at,
                plan.timing.earliest_offset_minutes,
                plan.timing.preferred_offset_minutes,
                plan.timing.expires_offset_minutes,
            )
        except TimingValidationError as exc:
            issues.append(ValidationIssue("invalid_timing", str(exc), "timing"))

    active = plan.should_initiate and goal != PlanGoal.SILENT.value
    if active and plan.timing is None:
        issues.append(ValidationIssue("missing_timing", "active plans require timing", "timing"))
    if active and not plan.topic_ref:
        issues.append(ValidationIssue("missing_topic_ref", "active plans require topic_ref", "topic_ref"))
    if active and not plan.evidence_refs:
        issues.append(
            ValidationIssue("missing_evidence_refs", "active plans require evidence_refs", "evidence_refs")
        )

    if any(not isinstance(ref, str) or not ref.strip() for ref in plan.evidence_refs):
        issues.append(ValidationIssue("invalid_evidence_ref", "evidence_refs must be non-empty strings"))
    if len(set(plan.evidence_refs)) != len(plan.evidence_refs):
        issues.append(ValidationIssue("duplicate_evidence_ref", "evidence_refs must be unique"))
    if available_evidence_refs is not None:
        available = set(available_evidence_refs)
        unknown = [ref for ref in plan.evidence_refs if ref not in available]
        if unknown:
            issues.append(
                ValidationIssue(
                    "unknown_evidence_ref",
                    f"evidence_refs are not present in context: {unknown!r}",
                    "evidence_refs",
                )
            )
    return issues


def check_plan(
    plan: InitiativePlan,
    *,
    available_evidence_refs: Optional[Iterable[str]] = None,
) -> ValidationResult:
    """Inspect a plan without raising an exception."""

    issues = _plan_issues(plan, available_evidence_refs=available_evidence_refs)
    return ValidationResult(not issues, tuple(issues))


def validate_plan(
    plan: InitiativePlan,
    *,
    available_evidence_refs: Optional[Iterable[str]] = None,
) -> InitiativePlan:
    """Validate and return the same plan, or raise ``PlanValidationError``."""

    result = check_plan(plan, available_evidence_refs=available_evidence_refs)
    if not result.valid:
        raise PlanValidationError(result.issues)
    return plan


def validate_timing(timing: PlanTiming) -> PlanTiming:
    """Validate and return a timing object."""

    if not isinstance(timing, PlanTiming):
        raise TimingValidationError("timing must be a PlanTiming")
    PlanTiming(
        timing.observed_at,
        timing.earliest_offset_minutes,
        timing.preferred_offset_minutes,
        timing.expires_offset_minutes,
    )
    return timing


@dataclass(frozen=True)
class PostDialogueOpportunity:
    """Internal harness event; it is deliberately not a conversation message."""

    observed_at: datetime
    last_dialogue_at: Optional[datetime] = None
    source: Literal["test_harness"] = "test_harness"
    event_type: Literal["post_dialogue_opportunity"] = "post_dialogue_opportunity"

    def __post_init__(self) -> None:
        require_timezone_aware(self.observed_at, field="observed_at")
        if self.last_dialogue_at is not None:
            require_timezone_aware(self.last_dialogue_at, field="last_dialogue_at")
        if self.source != "test_harness" or self.event_type != "post_dialogue_opportunity":
            raise InitiativeContractError("invalid internal post-dialogue event identity")


__all__ = [
    "ALLOWED_PLAN_GOALS",
    "EvidenceValidationError",
    "FORBIDDEN_PLAN_GOALS",
    "ForbiddenGoalError",
    "GoalValidationError",
    "InitiativeContractError",
    "InitiativePlan",
    "Plan",
    "PlanGoal",
    "PlanTiming",
    "PlanValidationError",
    "PostDialogueOpportunity",
    "TimingValidationError",
    "ValidationIssue",
    "ValidationResult",
    "check_plan",
    "is_timezone_aware",
    "require_timezone_aware",
    "validate_plan",
    "validate_timing",
]
