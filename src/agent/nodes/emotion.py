from __future__ import annotations

import random

from agent.config import AgentConfig
from agent.state import AgentState
from agent.utils import clamp

DELTA_MAP = {
    "normal": -0.08,
    "negative_feedback": 0.25,
    "sensitive_topic": 0.35,
    "task_request": 0.1,
    "questioning": 0.2,
    "praise": -0.15,
    "flirt": -0.10,
}

TSUNDERE_BONUS = 0.15
BURST_BONUS = 0.30
BASE_DECAY = 0.03


def update_emotion(state: AgentState, config: AgentConfig) -> AgentState:
    emotion = state.get("emotion", 0.0)
    category = state.get("category", "normal")
    strategy = state.get("strategy", "normal")
    delta = DELTA_MAP.get(category, -0.05)
    intensity = state.get("defect_intensity", config.defect_intensity)
    volatility = state.get("volatility", config.volatility)
    traits = state.get("traits", config.traits)
    burst_pending = state.get("burst_pending", False)
    turn_count = state.get("turn_count", 0)

    decay = BASE_DECAY
    if turn_count > 5:
        decay = BASE_DECAY * (5.0 / max(turn_count, 1))

    if category == "negative_feedback" and traits.get("tsundere", 0.0) >= 0.7:
        delta += TSUNDERE_BONUS

    if burst_pending:
        delta += BURST_BONUS

    if category in ("praise", "flirt"):
        delta += 0.30
        decay *= 0.5

    if strategy == "tsundere_retort":
        delta += 0.1
    elif strategy == "excuse":
        delta -= 0.05
    elif strategy == "gaslight":
        delta += 0.05
    elif strategy == "self_contradict":
        delta += 0.08
    elif strategy == "over_associate":
        delta -= 0.03
    elif strategy == "incorrect_correct":
        delta += 0.07
    elif strategy == "sudden_competence":
        delta -= 0.12
    elif strategy == "emotion_burst":
        delta += 0.2

    jitter = random.uniform(-config.emotion_jitter, config.emotion_jitter)

    if burst_pending:
        jitter += random.uniform(0, config.emotion_jitter * 2)

    new_emotion = clamp(
        emotion + delta * volatility * intensity - decay + jitter,
        config.emotion_bounds[0],
        config.emotion_bounds[1],
    )

    return {"emotion": new_emotion}
