from __future__ import annotations

import random

from agent.config import AgentConfig
from agent.state import AgentState, ActionStance


def _weighted_pick(options: list[tuple[ActionStance, float]]) -> ActionStance:
    total = sum(max(0.0, weight) for _, weight in options)
    if total <= 0:
        return options[0][0]

    roll = random.random() * total
    cursor = 0.0
    for stance, weight in options:
        cursor += max(0.0, weight)
        if roll <= cursor:
            return stance
    return options[-1][0]


def _recent_repeat_count(items: list[str]) -> int:
    if not items:
        return 0
    last = items[-1]
    count = 0
    for item in reversed(items):
        if item == last:
            count += 1
        else:
            break
    return count


def _merge_options(options: list[tuple[ActionStance, float]]) -> list[tuple[ActionStance, float]]:
    merged: dict[ActionStance, float] = {}
    for stance, weight in options:
        merged[stance] = merged.get(stance, 0.0) + max(0.0, weight)
    return [(stance, weight) for stance, weight in merged.items()]


def _base_options(category: str, emotion_low: bool, emotion_high: bool) -> list[tuple[ActionStance, float]]:
    if category == "creative_task":
        return [("dismissive", 0.70), ("deadpan", 0.20), ("tsundere_service", 0.10)]
    if category == "sensitive_topic":
        if emotion_high:
            return [("defensive_counter", 0.45), ("dismissive", 0.35), ("deadpan", 0.20)]
        return [("dismissive", 0.55), ("deadpan", 0.30), ("defensive_counter", 0.15)]
    if category == "negative_feedback":
        return [
            ("defensive_counter", 0.42 if emotion_high else 0.28),
            ("authoritative_bluffing", 0.22),
            ("tsundere_service", 0.20),
            ("deadpan", 0.16 if emotion_low else 0.10),
            ("dismissive", 0.08),
        ]
    if category == "farewell":
        return [("tsundere_service", 0.40), ("vulnerable_leak", 0.25), ("dismissive", 0.20), ("deadpan", 0.15)]
    if category in ("praise", "flirt"):
        return [
            ("vulnerable_leak", 0.42 if emotion_high else 0.28),
            ("tsundere_service", 0.34),
            ("deadpan", 0.14),
            ("dismissive", 0.10),
        ]
    if category == "task_request":
        options: list[tuple[ActionStance, float]] = [
            ("tsundere_service", 0.36),
            ("sudden_competence", 0.28),
            ("authoritative_bluffing", 0.12),
            ("deadpan", 0.10),
            ("dismissive", 0.08),
        ]
        if emotion_high:
            options.append(("emotion_burst", 0.18))
        return options
    if category == "questioning":
        return [
            ("authoritative_bluffing", 0.36),
            ("defensive_counter", 0.24 if emotion_high else 0.16),
            ("deadpan", 0.22 if emotion_low else 0.16),
            ("tsundere_service", 0.16),
            ("dismissive", 0.10),
        ]

    return [
        ("tsundere_service", 0.24),
        ("chaotic_rant", 0.22),
        ("authoritative_bluffing", 0.20),
        ("dismissive", 0.14),
        ("deadpan", 0.10),
        ("vulnerable_leak", 0.10),
    ]


def _apply_judge_adjustments(
    options: list[tuple[ActionStance, float]],
    event_analysis: dict,
) -> list[tuple[ActionStance, float]]:
    event_type = str(event_analysis.get("event_type", "")).lower()
    tone = str(event_analysis.get("tone", "")).lower()
    relationship = str(event_analysis.get("relationship_signal", "")).lower()
    risk = event_analysis.get("risk", 0.0)
    try:
        risk_value = float(risk)
    except (TypeError, ValueError):
        risk_value = 0.0

    adjusted: list[tuple[ActionStance, float]] = []
    for stance, weight in options:
        if event_type in ("praise", "flirt") or relationship == "closer":
            if stance == "vulnerable_leak":
                weight *= 1.45
            elif stance in ("dismissive", "authoritative_bluffing"):
                weight *= 0.75
        if event_type in ("hostile", "boundary") or risk_value >= 0.45:
            if stance in ("defensive_counter", "dismissive", "deadpan"):
                weight *= 1.30
            elif stance == "vulnerable_leak":
                weight *= 0.55
        if event_type in ("question", "confusion", "tease") or tone in ("sarcastic", "mocking"):
            if stance in ("authoritative_bluffing", "deadpan", "defensive_counter"):
                weight *= 1.20
        if event_type in ("command", "request"):
            if stance in ("sudden_competence", "tsundere_service"):
                weight *= 1.22
            elif stance == "dismissive":
                weight *= 0.70
        if relationship == "distant" and stance in ("dismissive", "deadpan"):
            weight *= 1.18
        adjusted.append((stance, weight))

    return _merge_options(adjusted)


def _avoid_repeated_stance(
    options: list[tuple[ActionStance, float]],
    stance_history: list[str],
) -> list[tuple[ActionStance, float]]:
    if not stance_history:
        return options

    last = stance_history[-1]
    repeat_count = _recent_repeat_count(stance_history)
    if repeat_count >= 2:
        alternatives = [(stance, weight) for stance, weight in options if stance != last]
        if alternatives:
            return alternatives

    penalty = 0.45 if repeat_count == 1 else 0.15
    return [
        (stance, weight * penalty if stance == last else weight)
        for stance, weight in options
    ]

def decide_defect_strategy(state: AgentState, config: AgentConfig) -> AgentState:
    category = state.get("category", "normal")
    emotion = state.get("emotion", 0.0)

    emotion_low = emotion < -0.3
    emotion_high = emotion >= 0.3

    stance_history = list(state.get("stance_history", []))
    options = _base_options(category, emotion_low, emotion_high)
    options = _apply_judge_adjustments(options, state.get("event_analysis", {}))

    fake_praise = state.get("fake_praise", False)
    if fake_praise:
        options = [("deadpan", 0.55), ("defensive_counter", 0.35), ("authoritative_bluffing", 0.10)]

    options = _avoid_repeated_stance(options, stance_history)
    stance = _weighted_pick(options)

    consecutive_same = 1
    for previous in reversed(stance_history):
        if previous == stance:
            consecutive_same += 1
        else:
            break

    return {
        "action_stance": stance,
        "consecutive_same_stance": consecutive_same,
    }
