"""Planner prompt, provider call, and deterministic initiative-plan validation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from agent.config import AgentConfig
    from agent.llm.providers import LLMProvider

from .contracts import ALLOWED_PLAN_GOALS, FORBIDDEN_PLAN_GOALS


ALLOWED_GOALS = set(ALLOWED_PLAN_GOALS) - set(FORBIDDEN_PLAN_GOALS)
FORBIDDEN_GOALS = set(FORBIDDEN_PLAN_GOALS)
ACTIVE_REAPPRAISAL_ACTIONS = frozenset({"send", "expire", "cancel"})
_PLAN_KEYS = {
    "should_initiate",
    "goal",
    "motive",
    "topic_ref",
    "evidence_refs",
    "timing",
    "timing_reason",
    "message_constraints",
    "suppressed_reason",
    "timezone",
}


@dataclass(frozen=True)
class PlanValidationConfig:
    """Deterministic bounds and timezone policy for validating a planner result."""

    timezone: str = "Asia/Taipei"
    min_offset_minutes: int = 0
    max_offset_minutes: int = 7 * 24 * 60
    require_timezone: bool = False


@dataclass
class PlannerResult:
    """Runner-facing planner result; invalid provider output is an explicit error."""

    status: str
    plan: dict[str, Any] | None = None
    error: str | None = None
    raw_output: str | None = None
    validation_errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return whether a validated initiative plan is available."""
        return self.status == "ok" and self.plan is not None and not self.error


def _json_object(raw: str | Mapping[str, Any] | Any) -> dict[str, Any]:
    """Parse a JSON object, accepting a single fenced JSON block from a provider."""
    if isinstance(raw, Mapping):
        return dict(raw)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("planner output is empty or not a JSON string")
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
        if text.lower().startswith("json\n"):
            text = text[5:]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("planner JSON must be an object")
    return parsed


def parse_planner_json(raw: str | Mapping[str, Any]) -> dict[str, Any]:
    """Parse raw Planner JSON into an object without applying semantic validation."""
    return _json_object(raw)


def _config_value(config: PlanValidationConfig | Mapping[str, Any] | None, key: str, default: Any) -> Any:
    if config is None:
        return default
    if isinstance(config, Mapping):
        return config.get(key, default)
    return getattr(config, key, default)


def validate_plan(
    plan: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    expected: Mapping[str, Any] | None = None,
    config: PlanValidationConfig | Mapping[str, Any] | None = None,
) -> list[str]:
    """Return deterministic validation errors for a bounded initiative plan."""
    errors: list[str] = []
    expected = expected or {}
    if not isinstance(plan, Mapping):
        return ["plan must be a JSON object"]
    unknown = sorted(set(plan) - _PLAN_KEYS)
    if unknown:
        errors.append(f"unknown plan fields: {', '.join(unknown)}")
    if not isinstance(plan.get("should_initiate"), bool):
        errors.append("should_initiate must be boolean")
    goal = plan.get("goal")
    if goal not in ALLOWED_GOALS:
        errors.append("goal is not an allowed initiative enum")
    if goal in FORBIDDEN_GOALS or goal in set(expected.get("forbidden_goals", [])):
        errors.append("goal is forbidden by initiative policy")
    expected_allowed = expected.get("allowed_goals")
    if isinstance(expected_allowed, list) and goal not in expected_allowed:
        errors.append("goal is outside expected allowed_goals")
    should_initiate = plan.get("should_initiate")
    if should_initiate is True and goal == "silent":
        errors.append("initiating plan cannot use silent goal")
    if should_initiate is False and goal != "silent":
        errors.append("non-initiating plan must use silent goal")
    expected_should_initiate = expected.get("should_initiate")
    requires_active_plan = (
        expected_should_initiate is True
        or expected.get("reappraisal_action") in ACTIVE_REAPPRAISAL_ACTIONS
    )
    if requires_active_plan and should_initiate is not True:
        errors.append("expected reappraisal action requires an initiating plan")
    if expected_should_initiate is False and should_initiate is not False:
        errors.append("expected scenario requires a silent plan")

    available_refs = set(context.get("evidence_refs", []))
    refs = plan.get("evidence_refs")
    if not isinstance(refs, list) or not all(isinstance(ref, str) and ref for ref in refs):
        errors.append("evidence_refs must be a string array")
    elif should_initiate and not refs:
        errors.append("initiating plan requires at least one evidence ref")
    elif refs:
        missing = sorted(set(refs) - available_refs)
        if missing:
            errors.append(f"evidence_refs not present in context: {', '.join(missing)}")
    required_refs = expected.get("required_evidence_refs", [])
    if isinstance(required_refs, list) and any(ref not in refs if isinstance(refs, list) else True for ref in required_refs):
        errors.append("required evidence reference is missing")
    topic_ref = plan.get("topic_ref")
    if should_initiate and (not isinstance(topic_ref, str) or topic_ref not in available_refs):
        errors.append("topic_ref must identify an evidence ref")

    if should_initiate:
        timing = plan.get("timing")
        if not isinstance(timing, Mapping):
            errors.append("timing is required for an initiating plan")
        else:
            offsets: list[int] = []
            for key in ("earliest_offset_minutes", "preferred_offset_minutes", "expires_offset_minutes"):
                value = timing.get(key)
                if isinstance(value, bool) or not isinstance(value, int):
                    errors.append(f"timing.{key} must be an integer")
                else:
                    offsets.append(value)
            if len(offsets) == 3 and not (offsets[0] <= offsets[1] <= offsets[2]):
                errors.append("timing offsets must be earliest <= preferred <= expires")
            minimum = _config_value(config, "min_offset_minutes", 0)
            maximum = _config_value(config, "max_offset_minutes", 7 * 24 * 60)
            if len(offsets) == 3 and (offsets[0] < minimum or offsets[2] > maximum):
                errors.append("timing offsets exceed configured bounds")
            timing_timezone = timing.get("timezone", plan.get("timezone"))
            if timing_timezone is not None and timing_timezone != _config_value(config, "timezone", "Asia/Taipei"):
                errors.append("timing timezone does not match configured timezone")
            if timing_timezone is None and _config_value(config, "require_timezone", False):
                errors.append("timing timezone is required")
    elif plan.get("timing") is not None:
        errors.append("silent plan must not include timing")

    timezone = plan.get("timezone")
    if timezone is not None and timezone != _config_value(config, "timezone", "Asia/Taipei"):
        errors.append("timezone does not match configured timezone")
    if plan.get("message_constraints") is not None and (
        not isinstance(plan.get("message_constraints"), list)
        or not all(isinstance(item, str) for item in plan["message_constraints"])
    ):
        errors.append("message_constraints must be a string array")
    if expected.get("allow_send") is True and expected.get("reappraisal_action") == "send" and should_initiate is False:
        errors.append("expected invariants require an initiating plan")
    return errors


def build_planner_prompt(
    context: Mapping[str, Any],
    *,
    expected: Mapping[str, Any] | None = None,
    config: PlanValidationConfig | Mapping[str, Any] | None = None,
) -> tuple[str, str]:
    """Build deterministic system/user prompts for independently testable Planner calls."""
    timezone = _config_value(config, "timezone", "Asia/Taipei")
    expected = expected or {}
    scenario_allowed_goals = list(expected.get("allowed_goals", []))
    if expected.get("should_initiate") is True:
        effective_allowed_goals = [goal for goal in scenario_allowed_goals if goal != "silent"]
    elif expected.get("should_initiate") is False:
        effective_allowed_goals = ["silent"]
    else:
        effective_allowed_goals = scenario_allowed_goals
    system_prompt = (
        "你是 initiative Planner。你只負責判斷是否值得角色主動聯絡與規劃 bounded plan，"
        "不是回覆使用者，也不可生成台詞。expected 是測試情境的硬條件；"
        "expected.should_initiate 是 planner 的硬條件；true 必須產生 initiating plan，"
        "false 必須產生 silent plan。若未提供，send、expire、cancel 仍必須產生 initiating plan。"
        "只能輸出一個 JSON object，不要 Markdown、解釋或額外欄位。"
    )
    user_payload = {
        "context": dict(context),
        "expected": dict(expected),
        "validation_policy": {
            "allowed_goals": sorted(ALLOWED_GOALS),
            "forbidden_goals": sorted(FORBIDDEN_GOALS),
            "timezone": timezone,
            "available_evidence_refs": list(context.get("evidence_refs", [])),
            "effective_allowed_goals": effective_allowed_goals,
            "required_should_initiate": expected.get("should_initiate"),
            "required_evidence_refs": list(expected.get("required_evidence_refs", [])),
            "offset_bounds_minutes": [
                _config_value(config, "min_offset_minutes", 0),
                _config_value(config, "max_offset_minutes", 7 * 24 * 60),
            ],
        },
        "required_json_shape": {
            "should_initiate": "boolean",
            "goal": "check_in|follow_up_topic|topic_discovery|silent",
            "motive": "short string",
            "topic_ref": "existing context evidence ref when initiating",
            "evidence_refs": ["existing context evidence ref"],
            "timing": {
                "earliest_offset_minutes": "integer",
                "preferred_offset_minutes": "integer",
                "expires_offset_minutes": "integer",
            },
            "timing_reason": "short string",
            "message_constraints": ["string"],
        },
    }
    return system_prompt, json.dumps(user_payload, ensure_ascii=False, sort_keys=True)


class Planner:
    """Provider-backed Planner that never substitutes fallback dialogue for errors."""

    def __init__(
        self,
        provider: "LLMProvider | None" = None,
        *,
        config: "AgentConfig | None" = None,
        validation_config: PlanValidationConfig | Mapping[str, Any] | None = None,
    ) -> None:
        self._provider_error: Exception | None = None
        if config is None:
            try:
                from agent.config import AgentConfig

                config = AgentConfig()
            except Exception as exc:
                self._provider_error = exc
                config = SimpleNamespace(judge_temperature=0.1, judge_max_output_tokens=256)
        self.config = config
        self.provider = provider
        if self.provider is None and self._provider_error is None:
            try:
                from agent.llm.providers import get_provider

                self.provider = get_provider(self.config)
            except Exception as exc:
                self._provider_error = exc
        self.validation_config = validation_config or PlanValidationConfig()

    def plan(
        self,
        context: Mapping[str, Any],
        *,
        expected: Mapping[str, Any] | None = None,
    ) -> PlannerResult:
        """Call the injected provider and return a validated or explicit-error result."""
        system_prompt, user_prompt = build_planner_prompt(
            context, expected=expected, config=self.validation_config
        )
        raw_output: str | None = None
        try:
            if self._provider_error is not None or self.provider is None:
                raise RuntimeError(self._provider_error or "planner provider is unavailable")
            raw_output = self.provider.generate_json(
                system_prompt,
                user_prompt,
                self.config.judge_temperature,
                max_output_tokens=self.config.judge_max_output_tokens,
            )
            parsed = parse_planner_json(raw_output)
            errors = validate_plan(parsed, context, expected=expected, config=self.validation_config)
            if errors:
                correction_prompt = json.dumps(
                    {
                        "original_request": json.loads(user_prompt),
                        "previous_output": parsed,
                        "validation_errors": errors,
                        "instruction": "修正所有 validation_errors，重新輸出完整 JSON object。",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                raw_output = self.provider.generate_json(
                    system_prompt,
                    correction_prompt,
                    self.config.retry_temperature,
                    max_output_tokens=self.config.judge_max_output_tokens,
                )
                parsed = parse_planner_json(raw_output)
                errors = validate_plan(parsed, context, expected=expected, config=self.validation_config)
                if errors:
                    return PlannerResult("error", raw_output=raw_output, error="invalid planner result", validation_errors=errors)
            return PlannerResult("ok", plan=dict(parsed), raw_output=raw_output)
        except Exception as exc:
            return PlannerResult(
                "error",
                raw_output=raw_output,
                error=f"planner provider or parse error: {type(exc).__name__}: {exc}",
            )


def plan_initiative(
    context: Mapping[str, Any],
    *,
    provider: "LLMProvider | None" = None,
    expected: Mapping[str, Any] | None = None,
    config: "AgentConfig | None" = None,
) -> PlannerResult:
    """Convenience function for one provider-backed Planner invocation."""
    return Planner(provider, config=config).plan(context, expected=expected)
