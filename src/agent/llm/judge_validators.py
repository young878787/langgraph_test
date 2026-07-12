from __future__ import annotations

import json
from typing import Optional, Tuple

from agent.llm.judging import VALID_CATEGORIES, VALID_INTENT_TARGETS

VALID_EVENT_TYPES = {
    *VALID_CATEGORIES,
    "boundary",
    "command",
    "concern",
    "confusion",
    "hostile",
    "question",
    "request",
    "silence",
    "tease",
}
VALID_RELATIONSHIP_SIGNALS = {"closer", "distant", "neutral"}
VALID_STATE_DELTA_KEYS = {
    "mood",
    "energy",
    "tension",
    "intimacy",
    "embarrassment",
    "confidence",
    "playfulness",
    "annoyance",
    "masking",
    "dominance",
    "sadness",
    "hostility",
    "boundary_pressure",
}


def _extract_json(text: str) -> Optional[str]:
    trimmed = text.strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        return trimmed

    start = trimmed.find("{")
    end = trimmed.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return trimmed[start : end + 1]


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y")
    return False


def _bounded_float(value: object, default: float, low: float, high: float) -> tuple[float, bool]:
    if isinstance(value, bool):
        return default, False
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default, False
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return default, False
    return max(low, min(high, parsed)), low <= parsed <= high


def _canonical_state_delta(value: object, warnings: list[str]) -> dict[str, float]:
    if not isinstance(value, dict):
        if value is not None:
            warnings.append("state_delta_suggestion_invalid")
        return {}

    result: dict[str, float] = {}
    for key, raw_delta in value.items():
        if key not in VALID_STATE_DELTA_KEYS:
            warnings.append(f"state_delta_unknown:{key}")
            continue
        delta, valid = _bounded_float(raw_delta, 0.0, -0.2, 0.2)
        if not valid:
            warnings.append(f"state_delta_clamped:{key}")
        result[key] = delta
    return result


def parse_judge_output_v2(response: str) -> Tuple[Optional[dict[str, object]], str]:
    if not response or not response.strip():
        return None, "Judge LLM 無回應 (空字串或 None)"

    candidate = _extract_json(response)
    if candidate is None:
        return None, f"未找到 JSON 物件 (回應前80字: {response[:80]})"

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as e:
        return None, f"JSON 解析失敗: {e} (原始: {candidate[:120]})"
    if not isinstance(data, dict):
        return None, f"Judge 輸出必須是 JSON object (原始: {candidate[:120]})"

    category = data.get("category")
    if isinstance(category, str):
        category = category.strip().lower()

    if category not in VALID_CATEGORIES:
        return None, f"category 無效: '{category}' 不在 {VALID_CATEGORIES} (原始: {candidate[:120]})"

    target = data.get("target", "unknown")
    if isinstance(target, str):
        target = target.strip().lower()
    if target not in VALID_INTENT_TARGETS:
        target = "unknown"

    warnings: list[str] = []
    event_type = data.get("event_type", category)
    if isinstance(event_type, str):
        event_type = event_type.strip().lower()
    if event_type not in VALID_EVENT_TYPES:
        warnings.append(f"event_type_defaulted:{event_type}")
        event_type = category

    relationship_signal = data.get("relationship_signal", "neutral")
    if isinstance(relationship_signal, str):
        relationship_signal = relationship_signal.strip().lower()
    if relationship_signal not in VALID_RELATIONSHIP_SIGNALS:
        warnings.append(f"relationship_signal_defaulted:{relationship_signal}")
        relationship_signal = "neutral"

    intensity, intensity_valid = _bounded_float(data.get("intensity", 0.5), 0.5, 0.0, 1.0)
    risk, risk_valid = _bounded_float(data.get("risk", 0.0), 0.0, 0.0, 1.0)
    if not intensity_valid:
        warnings.append("intensity_clamped_or_defaulted")
    if not risk_valid:
        warnings.append("risk_clamped_or_defaulted")

    canonical = {
        "category": category,
        "event_type": event_type,
        "subtype": str(data.get("subtype", "")).strip().lower(),
        "tone": str(data.get("tone", "")).strip().lower(),
        "intensity": intensity,
        "risk": risk,
        "relationship_signal": relationship_signal,
        "ambiguous_flag": _coerce_bool(data.get("ambiguous", False)),
        "sarcasm_possible": _coerce_bool(data.get("sarcasm_possible", False)),
        "requires_action": _coerce_bool(data.get("requires_action", False)),
        "intent_target": target,
        "state_delta_suggestion": _canonical_state_delta(
            data.get("state_delta_suggestion", {}), warnings
        ),
        "validation_warnings": warnings,
    }
    return canonical, ""


def build_rule_event_analysis(category: str) -> dict[str, object]:
    event_type = category if category in VALID_EVENT_TYPES else "normal"
    return {
        "category": category,
        "event_type": event_type,
        "subtype": "",
        "tone": "",
        "intensity": 0.5,
        "risk": 0.0,
        "relationship_signal": "neutral",
        "ambiguous_flag": False,
        "sarcasm_possible": False,
        "requires_action": category in ("task_request", "creative_task"),
        "intent_target": "assistant" if category != "normal" else "unknown",
        "state_delta_suggestion": {},
        "validation_warnings": ["rule_fallback"],
    }
