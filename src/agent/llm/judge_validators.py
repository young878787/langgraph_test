from __future__ import annotations

import json
from typing import Optional, Tuple

from agent.llm.judging import VALID_CATEGORIES


def _extract_json(text: str) -> Optional[str]:
    trimmed = text.strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        return trimmed

    start = trimmed.find("{")
    end = trimmed.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return trimmed[start : end + 1]


def parse_judge_output_v2(response: str) -> Tuple[Optional[str], str]:
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

    return category, ""
