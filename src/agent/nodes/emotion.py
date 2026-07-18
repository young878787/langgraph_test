from __future__ import annotations

from agent.config import AgentConfig
from agent.state import AgentState
from agent.utils import clamp

BASE_DELTAS = {
    "praise": {"mood": 0.06, "confidence": 0.04, "embarrassment": 0.10, "intimacy": 0.03, "tension": 0.01},
    "tease": {"annoyance": 0.05, "playfulness": 0.08, "tension": 0.03, "intimacy": 0.02, "dominance": 0.04},
    "concern": {"mood": 0.04, "intimacy": 0.07, "tension": -0.03, "masking": -0.04, "confidence": 0.02},
    "hostile": {"mood": -0.08, "tension": 0.12, "annoyance": 0.12, "hostility": 0.05, "masking": 0.08, "intimacy": -0.05},
    "boundary": {"tension": 0.15, "annoyance": 0.10, "boundary_pressure": 0.18, "playfulness": -0.10, "dominance": 0.10},
    "silence": {"mood": -0.03, "tension": 0.05, "energy": -0.02, "playfulness": 0.02},
    "questioning": {"tension": 0.05, "annoyance": 0.03},
    "question": {"tension": 0.03},
    "creative_task": {"energy": 0.05, "playfulness": 0.02},
    "task_request": {"energy": 0.02, "tension": 0.01},
    "request": {"energy": 0.02, "tension": 0.01},
    "command": {"energy": 0.02, "tension": 0.03},
    "flirt": {"embarrassment": 0.15, "intimacy": 0.05, "playfulness": 0.05, "tension": 0.02},
    "negative_feedback": {"mood": -0.05, "annoyance": 0.05, "hostility": 0.02},
}

DECAY_RATES = {
    "embarrassment": 0.92,
    "tension": 0.95,
    "annoyance": 0.93,
    "hostility": 0.90,
    "boundary_pressure": 0.88,
    "playfulness": 0.97,
}

BASELINE_STATE = {
    "mood": 0.55,
    "energy": 0.60,
    "tension": 0.10,
    "intimacy": 0.20,
    "embarrassment": 0.0,
    "confidence": 0.50,
    "playfulness": 0.45,
    "annoyance": 0.0,
    "masking": 0.35,
    "dominance": 0.40,
    "sadness": 0.0,
    "hostility": 0.0,
    "boundary_pressure": 0.0,
}

ACTIVATION_WEIGHTS = {
    "energy": 0.35,
    "tension": 0.30,
    "embarrassment": 0.15,
    "annoyance": 0.10,
    "hostility": 0.10,
}
LLM_DELTA_BLEND = 0.20
PROJECTION_SCALE = 2.5


def should_apply_emotion_event(state: AgentState) -> bool:
    event_analysis = state.get("event_analysis", {})
    if (
        state.get("judge_source") == "rule"
        or event_analysis.get("appraisal_confidence") == "low"
    ):
        return False
    return not (
        state.get("category", "normal") == "normal"
        and len(state.get("user_input", "")) < 5
    )


def _repetition_factor(consecutive_same: int) -> float:
    if consecutive_same >= 4:
        return 0.35
    if consecutive_same >= 3:
        return 0.50
    if consecutive_same >= 2:
        return 0.75
    return 1.0


def project_activation(character_state: dict[str, float], bounds: tuple[float, float]) -> float:
    raw = sum(character_state.get(key, BASELINE_STATE[key]) * weight for key, weight in ACTIVATION_WEIGHTS.items())
    baseline = sum(BASELINE_STATE[key] * weight for key, weight in ACTIVATION_WEIGHTS.items())
    return clamp((raw - baseline) * PROJECTION_SCALE, bounds[0], bounds[1])


def _state_diff(before: dict[str, float], after: dict[str, float]) -> dict[str, float]:
    return {
        key: round(after.get(key, 0.0) - before.get(key, 0.0), 4)
        for key in BASELINE_STATE
        if abs(after.get(key, 0.0) - before.get(key, 0.0)) >= 0.0001
    }


def update_emotion(
    state: AgentState,
    config: AgentConfig,
    *,
    apply_event: bool = True,
) -> AgentState:
    category = state.get("category", "normal")
    last_category = state.get("last_category", "normal")
    consecutive_same = state.get("consecutive_same_category", 1)
    consecutive_same = consecutive_same + 1 if category == last_category else 1

    before = {
        key: float(state.get("character_state", {}).get(key, baseline))
        for key, baseline in BASELINE_STATE.items()
    }
    character_state = dict(before)
    event_analysis = state.get("event_analysis", {})
    event_type = str(event_analysis.get("event_type", category))
    event_intensity = float(event_analysis.get("intensity", 0.5))
    base_delta = BASE_DELTAS.get(event_type, BASE_DELTAS.get(category, {})) if apply_event else {}
    repetition_factor = _repetition_factor(consecutive_same)
    applied_base: dict[str, float] = {}
    applied_llm: dict[str, float] = {}

    for key, value in base_delta.items():
        delta = value * event_intensity * repetition_factor
        character_state[key] += delta
        applied_base[key] = round(delta, 4)

    if apply_event:
        suggestion = event_analysis.get("state_delta_suggestion", {})
        if isinstance(suggestion, dict):
            for key, value in suggestion.items():
                if key not in BASELINE_STATE or isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                delta = value * LLM_DELTA_BLEND * event_intensity
                character_state[key] += delta
                applied_llm[key] = round(delta, 4)

    for key, rate in DECAY_RATES.items():
        character_state[key] *= rate
    for key, baseline in BASELINE_STATE.items():
        character_state[key] += (baseline - character_state[key]) * 0.05
        character_state[key] = clamp(character_state[key], 0.0, 1.0)

    emotion = project_activation(character_state, config.emotion_bounds)
    tick_kind = "event+decay" if apply_event else "decay_only"
    transition_reason = {
        "kind": tick_kind,
        "event_type": event_type,
        "intensity": event_intensity,
        "repetition_factor": repetition_factor,
        "base_delta": applied_base,
        "llm_delta": applied_llm,
    }
    return {
        "emotion": emotion,
        "last_category": category,
        "consecutive_same_category": consecutive_same,
        "character_state": character_state,
        "character_state_diff": _state_diff(before, character_state),
        "state_transition_reason": transition_reason,
    }


def tick_emotion(state: AgentState, config: AgentConfig) -> AgentState:
    return update_emotion(state, config, apply_event=False)
