from __future__ import annotations

import json
from typing import Optional, Tuple

from agent.llm.judging import VALID_CATEGORIES, VALID_STRATEGIES


def _extract_json(text: str) -> Optional[str]:
    trimmed = text.strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        return trimmed

    start = trimmed.find("{")
    end = trimmed.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return trimmed[start : end + 1]


def parse_judge_output(response: str) -> Optional[Tuple[str, str]]:
    """舊介面，保留相容性。新程式請用 parse_judge_output_v2"""
    result, _ = parse_judge_output_v2(response)
    return result


def parse_judge_output_v2(response: str) -> Tuple[Optional[Tuple[str, str]], str]:
    """解析 Judge LLM 回傳的 JSON，並回傳錯誤原因字串

    Returns:
        (result, error):
          - result: (category, strategy) tuple，失敗時為 None
          - error:   成功時為空字串；失敗時為錯誤描述
    """
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
    strategy = data.get("strategy")
    if isinstance(category, str):
        category = category.strip().lower()
    if isinstance(strategy, str):
        strategy = strategy.strip().lower()

    if category not in VALID_CATEGORIES:
        return None, f"category 無效: '{category}' 不在 {VALID_CATEGORIES} (原始: {candidate[:120]})"
    if strategy not in VALID_STRATEGIES:
        return None, f"strategy 無效: '{strategy}' 不在 {VALID_STRATEGIES} (原始: {candidate[:120]})"

    return (category, strategy), ""
