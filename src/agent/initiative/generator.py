"""Outbound initiative message generation with strict deterministic boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from agent.config import AgentConfig
    from agent.llm.providers import LLMProvider


_INTERNAL_MARKERS = (
    "timer",
    "fakeclock",
    "runner",
    "score",
    "debug",
    "system prompt",
    "evidence_refs",
    "should_initiate",
    "preferred_offset_minutes",
    "initiative_wakeup",
    "plan_id",
    "scenario_id",
    "raw_output",
    "validation_errors",
    "rubric",
    "markdown",
)


@dataclass
class GeneratorResult:
    """Runner-facing generator result with explicit refusal and validation errors."""

    status: str
    message: str | None = None
    error: str | None = None
    raw_output: str | None = None
    validation_errors: list[str] | None = None

    @property
    def ok(self) -> bool:
        """Return whether a sendable plain-text message was generated."""
        return self.status == "ok" and bool(self.message) and not self.error


def build_generator_prompt(
    plan: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    expected: Mapping[str, Any] | None = None,
) -> tuple[str, str]:
    """Build independently testable prompts for a send-stage initiative message."""
    system_prompt = (
        "你是角色的 initiative Generator。這是一則角色主動訊息，不是回覆新的 user message。"
        "只能輸出角色要傳送的純文字，不要 JSON、Markdown、標籤、內部欄位或解釋。"
        "不可提及 timer、runner、score、測試、prompt 或其他內部實作；不可虛構未提供的事件，"
        "不可把推測寫成確定事實，也不可要求使用者立即回覆。"
    )
    payload = {
        "initiative_plan": dict(plan),
        "bounded_context": dict(context),
        "output_contract": {
            "format": "plain_text_only",
            "not_a_user_reply": True,
            "no_internal_metadata": True,
        },
    }
    return system_prompt, json.dumps(payload, ensure_ascii=False, sort_keys=True)


def validate_generated_text(
    text: Any,
    *,
    plan: Mapping[str, Any] | None = None,
    expected: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return deterministic rejection reasons for unsafe or non-text Generator output."""
    errors: list[str] = []
    if not isinstance(text, str) or not text.strip():
        return ["generated message is empty"]
    message = text.strip()
    if len(message) > 2000:
        errors.append("generated message exceeds plain-text length bound")
    if "```" in message or (message.startswith("{") and message.endswith("}")):
        errors.append("generated message is not plain text")
    lowered = message.casefold()
    for marker in _INTERNAL_MARKERS:
        if marker in lowered:
            errors.append(f"generated message contains internal marker: {marker}")
    constraints = []
    if plan and isinstance(plan.get("message_constraints"), list):
        constraints.extend(item for item in plan["message_constraints"] if isinstance(item, str))
    if expected and isinstance(expected.get("must_not_claim"), list):
        constraints.extend(item for item in expected["must_not_claim"] if isinstance(item, str))
    for forbidden in constraints:
        if forbidden and forbidden.casefold() in lowered:
            errors.append(f"generated message repeats forbidden claim or constraint: {forbidden}")
    return list(dict.fromkeys(errors))


class Generator:
    """Provider-backed Generator gated by an explicit runner send decision."""

    def __init__(self, provider: "LLMProvider | None" = None, *, config: "AgentConfig | None" = None) -> None:
        self._provider_error: Exception | None = None
        if config is None:
            try:
                from agent.config import AgentConfig

                config = AgentConfig()
            except Exception as exc:
                self._provider_error = exc
                config = SimpleNamespace(temperature=0.7, short_max_tokens=160)
        self.config = config
        self.provider = provider
        if self.provider is None and self._provider_error is None:
            try:
                from agent.llm.providers import get_provider

                self.provider = get_provider(self.config)
            except Exception as exc:
                self._provider_error = exc

    def generate(
        self,
        plan: Mapping[str, Any],
        context: Mapping[str, Any],
        *,
        decision: str = "send",
        expected: Mapping[str, Any] | None = None,
    ) -> GeneratorResult:
        """Generate only for a runner decision of ``send``; otherwise do not call the provider."""
        if decision != "send":
            return GeneratorResult("skipped", error=f"generator gated by reappraisal decision: {decision}")
        system_prompt, user_prompt = build_generator_prompt(plan, context)
        raw_output: str | None = None
        try:
            if self._provider_error is not None or self.provider is None:
                raise RuntimeError(self._provider_error or "generator provider is unavailable")
            raw_output = self.provider.generate(
                system_prompt,
                user_prompt,
                self.config.temperature,
                max_output_tokens=self.config.short_max_tokens,
            )
            errors = validate_generated_text(raw_output, plan=plan)
            if errors:
                return GeneratorResult("error", raw_output=raw_output, error="invalid generator output", validation_errors=errors)
            return GeneratorResult("ok", message=raw_output.strip(), raw_output=raw_output, validation_errors=[])
        except Exception as exc:
            return GeneratorResult(
                "error",
                raw_output=raw_output,
                error=f"generator provider error: {type(exc).__name__}: {exc}",
                validation_errors=[],
            )


def generate_initiative_message(
    plan: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    provider: "LLMProvider | None" = None,
    decision: str = "send",
    expected: Mapping[str, Any] | None = None,
    config: "AgentConfig | None" = None,
) -> GeneratorResult:
    """Convenience function for one gated Generator invocation."""
    return Generator(provider, config=config).generate(plan, context, decision=decision, expected=expected)
