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

    # 優先判斷敏感話題（觸發迴避/傲嬌模式）
    for topic in config.sensitive_topics:
        if topic in text:
            category = "sensitive_topic"
            trigger = topic
            break

    # 其次判斷質問（觸發說謊/煤氣燈模式）
    if category == "normal":
        for kw in config.questioning_keywords:
            if kw in text:
                category = "questioning"
                trigger = kw
                break

    # 再判斷任務請求（觸發找藉口模式）
    if category == "normal":
        for kw in config.task_request_keywords:
            if kw in text:
                category = "task_request"
                trigger = kw
                break

    # 最後判斷負面回饋（傲嬌/否認模式）
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
