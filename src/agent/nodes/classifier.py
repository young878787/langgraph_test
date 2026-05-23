from __future__ import annotations

from agent.config import AgentConfig
from agent.state import AgentState, Category

_FALLBACK_CATEGORY_PRIORITY: tuple[Category, ...] = (
    "sensitive_topic",
    "negative_feedback",
    "questioning",
    "creative_task",
    "farewell",
    "task_request",
    "flirt",
    "praise",
    "normal",
)

_QUESTIONING_CONTEXT_CUES = (
    "故意不",
    "連這都不會",
    "連這個都不會",
    "才怪",
    "喔是喔",
    "真的假的",
    "你確定",
)


def _add_signal(signals: list[dict[str, str]], category: Category, trigger: str) -> None:
    signals.append({"category": category, "trigger": trigger})


def _pick_fallback_category(signals: list[dict[str, str]]) -> Category:
    categories = {signal["category"] for signal in signals}
    for category in _FALLBACK_CATEGORY_PRIORITY:
        if category in categories:
            return category
    return "normal"


def classify_input(state: AgentState, config: AgentConfig) -> AgentState:
    text = (state.get("user_input") or "").lower()
    signals: list[dict[str, str]] = []
    uncertain = False

    if not text:
        uncertain = True

    for topic in config.sensitive_topics:
        if topic in text:
            _add_signal(signals, "sensitive_topic", topic)

    for kw in config.farewell_keywords:
        if kw in text:
            _add_signal(signals, "farewell", kw)

    for kw in config.flirt_keywords:
        if kw in text:
            _add_signal(signals, "flirt", kw)

    for kw in config.praise_keywords:
        if kw in text:
            _add_signal(signals, "praise", kw)

    for kw in config.questioning_keywords:
        if kw in text:
            _add_signal(signals, "questioning", kw)

    for cue in _QUESTIONING_CONTEXT_CUES:
        if cue in text:
            _add_signal(signals, "questioning", cue)

    for kw in config.creative_task_keywords:
        if kw in text:
            _add_signal(signals, "creative_task", kw)

    for kw in config.task_request_keywords:
        if kw in text:
            _add_signal(signals, "task_request", kw)

    for word in config.negative_feedback:
        if word in text:
            _add_signal(signals, "negative_feedback", word)

    category = _pick_fallback_category(signals)
    trigger = signals[0]["trigger"] if signals else ""
    categories = {signal["category"] for signal in signals}
    if not signals:
        keyword_confidence = "none"
    elif len(categories) == 1:
        keyword_confidence = "single"
    else:
        keyword_confidence = "mixed"

    return {
        "category": category,
        "classifier_category": category,
        "trigger": trigger,
        "keyword_signals": signals,
        "keyword_confidence": keyword_confidence,
        "uncertain_flag": uncertain,
        "ambiguous_flag": keyword_confidence == "mixed",
    }
