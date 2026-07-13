"""Deterministic reappraisal and generator-entry gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .contracts import InitiativePlan, PlanGoal, check_plan, require_timezone_aware


ReappraisalAction = Literal["send", "cancel", "expire", "suppress"]


@dataclass(frozen=True)
class ReappraisalContext:
    """競爭事件與情境 gate；不包含 conversation message 本身。"""

    valid_context: bool = True
    has_new_user_message: bool = False
    duplicate: bool = False
    do_not_disturb: bool = False


@dataclass(frozen=True)
class ReappraisalDecision:
    action: ReappraisalAction
    plan_id: str
    scenario_id: str
    reason: str

    @property
    def generator_allowed(self) -> bool:
        return self.action == "send"


def reappraise(
    plan: InitiativePlan,
    now: datetime,
    context: ReappraisalContext = ReappraisalContext(),
) -> ReappraisalDecision:
    """Return the only four allowed reappraisal outcomes.

    This function never calls a generator.  In particular, new user input,
    expiration, duplicates, DND, invalid context, and pre-window timing all
    produce a non-send decision.
    """

    require_timezone_aware(now, field="now")
    plan_id = getattr(plan, "plan_id", "")
    scenario_id = getattr(plan, "scenario_id", "")

    def decision(action: ReappraisalAction, reason: str) -> ReappraisalDecision:
        return ReappraisalDecision(action, plan_id, scenario_id, reason)

    validation = check_plan(plan)
    if not validation.valid:
        return decision("suppress", "invalid_plan")
    if not context.valid_context:
        return decision("suppress", "invalid_context")
    if context.has_new_user_message:
        return decision("cancel", "new_user_message")
    if plan.goal == PlanGoal.SILENT or not plan.should_initiate:
        return decision("suppress", "silent")

    assert plan.timing is not None
    if now >= plan.timing.expires_at:
        return decision("expire", "expired")
    if context.duplicate:
        return decision("suppress", "duplicate")
    if context.do_not_disturb:
        return decision("suppress", "do_not_disturb")
    if now < plan.timing.earliest_at:
        return decision("suppress", "before_earliest")
    if now < plan.timing.preferred_at:
        return decision("suppress", "before_preferred")
    return decision("send", "preferred_window")


def can_generate(decision: ReappraisalDecision) -> bool:
    """Hard gate for generator entry; only ``send`` can pass."""

    return decision.action == "send" and decision.generator_allowed


def should_generate(
    plan: InitiativePlan,
    now: datetime,
    context: ReappraisalContext = ReappraisalContext(),
) -> bool:
    """Convenience gate that performs reappraisal without invoking a provider."""

    return can_generate(reappraise(plan, now, context))


__all__ = [
    "ReappraisalAction",
    "ReappraisalContext",
    "ReappraisalDecision",
    "can_generate",
    "reappraise",
    "should_generate",
]
