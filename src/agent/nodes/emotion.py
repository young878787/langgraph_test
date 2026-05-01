from __future__ import annotations

from agent.config import AgentConfig
from agent.state import AgentState
from agent.utils import clamp

DELTA_MAP = {
    "normal": -0.08,
    "negative_feedback": 0.2,
    "sensitive_topic": 0.35,
}


def update_emotion(state: AgentState, config: AgentConfig) -> AgentState:
    emotion = state.get("emotion", 0.0)
    category = state.get("category", "normal")
    delta = DELTA_MAP.get(category, -0.05)
    intensity = state.get("defect_intensity", config.defect_intensity)
    volatility = state.get("volatility", config.volatility)
    decay = state.get("emotion_decay", config.emotion_decay)

    new_emotion = clamp(
        emotion + delta * volatility * intensity - decay,
        config.emotion_bounds[0],
        config.emotion_bounds[1],
    )

    return {"emotion": new_emotion}
