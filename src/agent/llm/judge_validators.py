from __future__ import annotations

import json
from typing import Optional, Tuple

from agent.llm.judging import VALID_CATEGORIES, VALID_INTENT_TARGETS


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

    return {
        "category": category,
        "ambiguous_flag": _coerce_bool(data.get("ambiguous", False)),
        "sarcasm_possible": _coerce_bool(data.get("sarcasm_possible", False)),
        "requires_action": _coerce_bool(data.get("requires_action", False)),
        "intent_target": target,
    }, ""
