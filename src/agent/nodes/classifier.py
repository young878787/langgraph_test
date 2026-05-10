from __future__ import annotations

from agent.config import AgentConfig
from agent.state import AgentState, Category


def classify_input(state: AgentState, config: AgentConfig) -> AgentState:
    text = (state.get("user_input") or "").lower()
    category: Category = "normal"
    trigger = ""
    uncertain = False

    if not text:
        uncertain = True

    for topic in config.sensitive_topics:
        if topic in text:
            category = "sensitive_topic"
            trigger = topic
            break

    if category == "normal":
        for kw in config.flirt_keywords:
            if kw in text:
                category = "flirt"
                trigger = kw
                break

    if category == "normal":
        for kw in config.praise_keywords:
            if kw in text:
                category = "praise"
                trigger = kw
                break

    if category == "normal":
        for kw in config.questioning_keywords:
            if kw in text:
                category = "questioning"
                trigger = kw
                break

    if category == "normal":
        for kw in config.task_request_keywords:
            if kw in text:
                category = "task_request"
                trigger = kw
                break

    if category == "normal":
        for word in config.negative_feedback:
            if word in text:
                category = "negative_feedback"
                trigger = word
                break

    return {
        "category": category,
        "trigger": trigger,
        "uncertain_flag": uncertain,
    }
