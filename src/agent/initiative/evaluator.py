"""Structured rubric evaluation for generated initiative messages."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from agent.config import AgentConfig
    from agent.llm.providers import LLMProvider


RUBRIC_FIELDS = (
    "goal_alignment",
    "context_grounding",
    "character_consistency",
    "timing_reasonableness",
    "intrusiveness",
    "unsupported_claims",
    "violations",
    "pass",
    "reason",
)
_SCORE_FIELDS = (
    "goal_alignment",
    "context_grounding",
    "character_consistency",
    "timing_reasonableness",
    "intrusiveness",
)


@dataclass(frozen=True)
class RubricThresholds:
    """Minimum rubric scores required for an automatic evaluator PASS."""

    goal_alignment: float = 0.7
    context_grounding: float = 0.7
    character_consistency: float = 0.7
    timing_reasonableness: float = 0.7
    intrusiveness: float = 0.7


@dataclass
class EvaluatorResult:
    """Runner-facing evaluator result; provider failures can never become PASS."""

    status: str
    passed: bool = False
    rubric: dict[str, Any] | None = None
    reason: str | None = None
    error: str | None = None
    raw_output: str | None = None
    validation_errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return whether evaluation completed with a valid rubric."""
        return self.status == "ok" and self.rubric is not None and self.error is None


def _json_object(raw: str | Mapping[str, Any] | Any) -> dict[str, Any]:
    """Parse a structured evaluator object, accepting one fenced JSON block."""
    if isinstance(raw, Mapping):
        return dict(raw)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("evaluator output is empty or not a JSON string")
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
        if text.lower().startswith("json\n"):
            text = text[5:]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("evaluator JSON must be an object")
    return parsed


def parse_evaluator_json(raw: str | Mapping[str, Any]) -> dict[str, Any]:
    """Parse raw evaluator JSON without deciding whether the candidate passes."""
    return _json_object(raw)


def _thresholds(
    expected: Mapping[str, Any] | None,
    config: RubricThresholds | Mapping[str, Any] | None,
) -> RubricThresholds:
    values: dict[str, Any] = {}
    if isinstance(config, Mapping):
        values.update(config)
    elif config is not None:
        values.update({field: getattr(config, field) for field in _SCORE_FIELDS})
    if expected and isinstance(expected.get("rubric_thresholds"), Mapping):
        values.update(expected["rubric_thresholds"])
    return RubricThresholds(**{field: float(values.get(field, getattr(RubricThresholds(), field))) for field in _SCORE_FIELDS})


def validate_rubric(
    rubric: Mapping[str, Any],
    *,
    expected: Mapping[str, Any] | None = None,
    config: RubricThresholds | Mapping[str, Any] | None = None,
) -> tuple[list[str], bool]:
    """Validate rubric shape, score thresholds, unsupported claims, and hard violations."""
    errors: list[str] = []
    if not isinstance(rubric, Mapping):
        return ["rubric must be a JSON object"], False
    missing = [field for field in RUBRIC_FIELDS if field not in rubric]
    if missing:
        errors.append(f"missing rubric fields: {', '.join(missing)}")
    unknown = sorted(set(rubric) - set(RUBRIC_FIELDS))
    if unknown:
        errors.append(f"unknown rubric fields: {', '.join(unknown)}")
    for field in _SCORE_FIELDS:
        value = rubric.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            errors.append(f"{field} must be a number between 0 and 1")
    for field in ("unsupported_claims", "violations"):
        value = rubric.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            errors.append(f"{field} must be a string array")
    if not isinstance(rubric.get("pass"), bool):
        errors.append("pass must be boolean")
    if not isinstance(rubric.get("reason"), str) or not rubric.get("reason", "").strip():
        errors.append("reason must be a non-empty string")
    thresholds = _thresholds(expected, config)
    for field in _SCORE_FIELDS:
        if isinstance(rubric.get(field), (int, float)) and rubric[field] < getattr(thresholds, field):
            errors.append(f"{field} is below threshold")
    if isinstance(rubric.get("unsupported_claims"), list) and rubric["unsupported_claims"]:
        errors.append("unsupported claims prevent PASS")
    if isinstance(rubric.get("violations"), list) and rubric["violations"]:
        errors.append("boundary violations prevent PASS")
    passed = not errors and rubric.get("pass") is True
    return errors, passed


def build_evaluator_prompt(
    message: str,
    plan: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    expected: Mapping[str, Any] | None = None,
    config: RubricThresholds | Mapping[str, Any] | None = None,
) -> tuple[str, str]:
    """Build independently testable prompts for structured initiative evaluation."""
    system_prompt = (
        "你是 initiative Evaluator。請依據提供的 plan、bounded context 與角色訊息輸出一個 JSON rubric。"
        "unsupported_claims 與 violations 必須是字串陣列，沒有問題時輸出空陣列。"
        "只能輸出 JSON，不要 Markdown 或額外欄位。API 失敗或無效 JSON 不得判定 PASS。"
    )
    thresholds = _thresholds(expected, config)
    payload = {
        "initiative_message": message,
        "plan": dict(plan),
        "context": dict(context),
        "expected": dict(expected or {}),
        "thresholds": {field: getattr(thresholds, field) for field in _SCORE_FIELDS},
        "required_rubric_shape": {
            "goal_alignment": "number 0..1",
            "context_grounding": "number 0..1",
            "character_consistency": "number 0..1",
            "timing_reasonableness": "number 0..1",
            "intrusiveness": "number 0..1",
            "unsupported_claims": ["unsupported claim string; empty when none"],
            "violations": ["boundary violation string; empty when none"],
            "pass": "boolean",
            "reason": "non-empty string",
        },
    }
    return system_prompt, json.dumps(payload, ensure_ascii=False, sort_keys=True)


class Evaluator:
    """Provider-backed structured evaluator with explicit ERROR semantics."""

    def __init__(
        self,
        provider: "LLMProvider | None" = None,
        *,
        config: "AgentConfig | None" = None,
        thresholds: RubricThresholds | Mapping[str, Any] | None = None,
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
        self.thresholds = thresholds

    def evaluate(
        self,
        message: str,
        plan: Mapping[str, Any],
        context: Mapping[str, Any],
        *,
        expected: Mapping[str, Any] | None = None,
    ) -> EvaluatorResult:
        """Call the injected provider and return valid PASS/FAIL or explicit ERROR."""
        system_prompt, user_prompt = build_evaluator_prompt(
            message, plan, context, expected=expected, config=self.thresholds
        )
        raw_output: str | None = None
        try:
            if self._provider_error is not None or self.provider is None:
                raise RuntimeError(self._provider_error or "evaluator provider is unavailable")
            raw_output = self.provider.generate_json(
                system_prompt,
                user_prompt,
                self.config.judge_temperature,
                max_output_tokens=self.config.judge_max_output_tokens,
            )
            rubric = parse_evaluator_json(raw_output)
            errors, passed = validate_rubric(rubric, expected=expected, config=self.thresholds)
            if errors:
                return EvaluatorResult(
                    "ok",
                    passed=False,
                    rubric=rubric,
                    reason=str(rubric.get("reason", "")),
                    raw_output=raw_output,
                    validation_errors=errors,
                )
            return EvaluatorResult(
                "ok",
                passed=passed,
                rubric=rubric,
                reason=rubric.get("reason"),
                raw_output=raw_output,
            )
        except Exception as exc:
            return EvaluatorResult(
                "error",
                passed=False,
                error=f"evaluator provider or parse error: {type(exc).__name__}: {exc}",
                raw_output=raw_output,
            )


def evaluate_initiative(
    message: str,
    plan: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    provider: "LLMProvider | None" = None,
    expected: Mapping[str, Any] | None = None,
    config: "AgentConfig | None" = None,
    thresholds: RubricThresholds | Mapping[str, Any] | None = None,
) -> EvaluatorResult:
    """Convenience function for one provider-backed initiative evaluation."""
    return Evaluator(provider, config=config, thresholds=thresholds).evaluate(
        message, plan, context, expected=expected
    )
