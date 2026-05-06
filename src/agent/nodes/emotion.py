from __future__ import annotations

from agent.config import AgentConfig
from agent.state import AgentState
from agent.utils import clamp

DELTA_MAP = {
    "normal": -0.08,
    "negative_feedback": 0.25,  # 提高負面回饋的情緒影響
    "sensitive_topic": 0.35,
    "task_request": 0.1,  # 被要求做事也會有點不高興
    "questioning": 0.2,  # 被質疑會生氣
}

# 傲嬌加成：如果被罵且 tsundere 特質高，情緒上升更多
TSUNDERE_BONUS = 0.15


def update_emotion(state: AgentState, config: AgentConfig) -> AgentState:
    emotion = state.get("emotion", 0.0)
    category = state.get("category", "normal")
    strategy = state.get("strategy", "normal")
    delta = DELTA_MAP.get(category, -0.05)
    intensity = state.get("defect_intensity", config.defect_intensity)
    volatility = state.get("volatility", config.volatility)
    decay = state.get("emotion_decay", config.emotion_decay)
    traits = state.get("traits", config.traits)

    # 傲嬌加成：被罵時特別容易激動
    if category == "negative_feedback" and traits.get("tsundere", 0.0) >= 0.7:
        delta += TSUNDERE_BONUS

    # 策略加成：某些策略會影響情緒
    if strategy == "tsundere_retort":
        delta += 0.1  # 傲嬌反擊後情緒會更高
    elif strategy == "excuse":
        delta -= 0.05  # 找藉口後稍微冷靜
    elif strategy == "gaslight":
        delta += 0.05  # 說謊會讓情緒稍微上升

    new_emotion = clamp(
        emotion + delta * volatility * intensity - decay,
        config.emotion_bounds[0],
        config.emotion_bounds[1],
    )

    return {"emotion": new_emotion}
