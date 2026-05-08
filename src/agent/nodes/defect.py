from __future__ import annotations

import random

from agent.config import AgentConfig
from agent.state import AgentState, Strategy


def decide_defect_strategy(state: AgentState, config: AgentConfig) -> AgentState:
    category = state.get("category", "normal")
    emotion = state.get("emotion", 0.0)
    traits = state.get("traits", config.traits)
    uncertain = state.get("uncertain_flag", False)
    trigger_counters = state.get("trigger_counters", {})
    strategy_history = state.get("strategy_history", [])

    tsundere = traits.get("tsundere", 0.0)
    yandere = traits.get("yandere", 0.0)
    excuse_prone = traits.get("excuse_prone", 0.0)
    liar = traits.get("liar", 0.0)
    rambler = traits.get("rambler", 0.0)
    contradict_prone = traits.get("contradict_prone", 0.0)
    overthinker = traits.get("overthinker", 0.0)
    knowitall = traits.get("knowitall", 0.0)
    perfectionist = traits.get("perfectionist", 0.0)

    strategy: Strategy = "normal"
    defect_mode = "none"

    consecutive_same = 0
    if strategy_history:
        last = strategy_history[-1]
        for s in reversed(strategy_history):
            if s == last:
                consecutive_same += 1
            else:
                break

    last_was_burst = strategy_history and strategy_history[-1] == "emotion_burst"
    total_triggers = sum(trigger_counters.values())
    burst_pending = (
        not last_was_burst
        and total_triggers >= config.burst_threshold
        and random.random() < 0.4
    )

    if burst_pending:
        strategy = "emotion_burst"
        defect_mode = "burst"
        return {
            "strategy": strategy,
            "defect_mode": defect_mode,
            "consecutive_same_strategy": consecutive_same,
            "burst_pending": True,
        }

    if category == "sensitive_topic":
        if tsundere >= 0.7 and emotion >= 0.3 and random.random() < 0.4:
            strategy = "tsundere_retort"
            defect_mode = "tsundere"
        elif emotion >= 0.5:
            strategy = "avoid"
            defect_mode = "avoidance"
        else:
            strategy = "deflect"
            defect_mode = "avoidance"

    elif category == "negative_feedback":
        if tsundere >= 0.7:
            strategy = "tsundere_retort"
            defect_mode = "tsundere"
        elif emotion >= 0.6:
            strategy = "deny"
            defect_mode = "angry_denial"
        else:
            strategy = "defend"
            defect_mode = "defend"

    elif category == "task_request":
        if burst_pending:
            strategy = "emotion_burst"
            defect_mode = "burst"
        elif contradict_prone >= 0.5 and random.random() < contradict_prone:
            strategy = "self_contradict"
            defect_mode = "self_contradict"
        elif excuse_prone >= 0.5 and random.random() < excuse_prone:
            strategy = "excuse"
            defect_mode = "excuse"
        else:
            strategy = "normal"
            defect_mode = "cooperative_for_once"

    elif category == "questioning":
        if liar >= 0.5 and random.random() < liar:
            strategy = "gaslight"
            defect_mode = "gaslight"
        elif knowitall >= 0.5 and random.random() < knowitall:
            strategy = "incorrect_correct"
            defect_mode = "incorrect_correct"
        else:
            strategy = "defend"
            defect_mode = "honest_defense"

    else:
        last_was_overthink = strategy_history and strategy_history[-1] == "over_associate"
        overthink_chance = overthinker - 0.5
        if last_was_overthink:
            overthink_chance *= 0.5

        if uncertain and rambler >= 0.5:
            strategy = "nonsense"
            defect_mode = "rambling"
        elif emotion >= 0.7 and yandere >= 0.6:
            strategy = "defend"
            defect_mode = "yandere_protect"
        elif overthinker >= 0.6 and random.random() < overthink_chance:
            strategy = "over_associate"
            defect_mode = "over_associate"
        elif perfectionist >= 0.3 and random.random() < 0.08:
            strategy = "sudden_competence"
            defect_mode = "sudden_competence"
        elif rambler >= 0.7 and random.random() < (rambler - 0.5):
            strategy = "nonsense"
            defect_mode = "random_ramble"

    return {
        "strategy": strategy,
        "defect_mode": defect_mode,
        "consecutive_same_strategy": consecutive_same,
        "burst_pending": burst_pending,
    }
