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
    candidate = _extract_json(response)
    if candidate is None:
        return None

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None

    category = data.get("category")
    strategy = data.get("strategy")
    if isinstance(category, str):
        category = category.strip().lower()
    if isinstance(strategy, str):
        strategy = strategy.strip().lower()

    if category not in VALID_CATEGORIES or strategy not in VALID_STRATEGIES:
        return None

    return category, strategy
