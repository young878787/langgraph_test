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
    "praise": 0.05,
    "flirt": -0.10,
    "farewell": -0.05,
}

TSUNDERE_BONUS = 0.15
BURST_BONUS = 0.30
BASE_DECAY = 0.03
AFFECTION_BONUS = 0.24
AFFECTION_DECAY_FLOOR = 0.25
HIGH_EMOTION_THRESHOLD = 0.70
HIGH_EMOTION_POSITIVE_SCALE = 0.45
NORMAL_COOLDOWN_STEP = 0.5
NORMAL_COOLDOWN_CAP = 4


def update_emotion(state: AgentState, config: AgentConfig) -> AgentState:
    emotion = state.get("emotion", 0.0)
    category = state.get("category", "normal")
    stance = state.get("action_stance", "normal")
    delta = DELTA_MAP.get(category, -0.05)
    intensity = state.get("defect_intensity", config.defect_intensity)
    volatility = state.get("volatility", config.volatility)
    traits = state.get("traits", config.traits)
    burst_pending = state.get("burst_pending", False)
    turn_count = state.get("turn_count", 0)
    last_category = state.get("last_category", "normal")
    consecutive_same = state.get("consecutive_same_category", 1)
    if category == last_category:
        consecutive_same += 1
    else:
        consecutive_same = 1

    base_decay = state.get("emotion_decay", config.emotion_decay or BASE_DECAY)
    decay = base_decay * (1.0 + turn_count / 10.0)

    if category == "negative_feedback" and traits.get("tsundere", 0.0) >= 0.7:
        delta += TSUNDERE_BONUS

    if burst_pending:
        delta += BURST_BONUS

    if category in ("praise", "flirt"):
        positive_room = max(0.0, 1.0 - max(emotion, 0.0))
        affection_scale = max(AFFECTION_DECAY_FLOOR, positive_room)
        delta += AFFECTION_BONUS * affection_scale
        decay *= 0.8

    if stance == "defensive_counter":
        delta += 0.1
    elif stance == "dismissive":
        delta -= 0.05
    elif stance == "authoritative_bluffing":
        delta += 0.07
    elif stance == "chaotic_rant":
        delta += 0.08
    elif stance == "vulnerable_leak":
        delta -= 0.03
    elif stance == "sudden_competence":
        delta -= 0.12
    elif stance == "emotion_burst":
        delta += 0.2

    adaptation = 1.0 / (1.0 + (consecutive_same - 1) * 0.3)
    delta *= adaptation

    if category == "normal" and consecutive_same > 1 and turn_count > 1:
        cooldown_steps = min(consecutive_same - 1, NORMAL_COOLDOWN_CAP)
        decay += base_decay * NORMAL_COOLDOWN_STEP * cooldown_steps

    if emotion > HIGH_EMOTION_THRESHOLD and delta > 0:
        delta *= HIGH_EMOTION_POSITIVE_SCALE

    jitter = random.uniform(-config.emotion_jitter, config.emotion_jitter)

    if burst_pending:
        jitter += random.uniform(0, config.emotion_jitter * 2)

    new_emotion = clamp(
        emotion + delta * volatility * intensity - decay + jitter,
        config.emotion_bounds[0],
        config.emotion_bounds[1],
    )

    return {
        "emotion": new_emotion,
        "last_category": category,
        "consecutive_same_category": consecutive_same,
    }
