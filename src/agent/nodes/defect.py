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
        return {
            "strategy": strategy,
            "consecutive_same_strategy": consecutive_same,
            "burst_pending": True,
        }

    emotion_low = emotion < -0.3

    if category == "creative_task":
        if emotion >= 0.5:
            strategy = random.choice(["deflect", "excuse"])
        elif tsundere >= 0.6 and random.random() < 0.7:
            strategy = "deflect"
        elif excuse_prone >= 0.5 and random.random() < 0.5:
            strategy = "excuse"
        elif rambler >= 0.5 and random.random() < 0.4:
            strategy = "nonsense"
        else:
            strategy = "avoid"

    elif category == "sensitive_topic":
        if tsundere >= 0.7 and emotion >= 0.3 and random.random() < 0.4:
            strategy = "tsundere_retort"
        elif emotion >= 0.5:
            strategy = "avoid"
        else:
            strategy = "deflect"

    elif category == "negative_feedback":
        if tsundere >= 0.7:
            strategy = "tsundere_retort"
        elif emotion >= 0.6:
            strategy = "deny"
        else:
            strategy = "defend"

    elif category == "praise":
        strategy = "tsundere_retort"

    elif category == "flirt":
        if tsundere >= 0.7:
            strategy = "tsundere_retort"
        else:
            strategy = "defend"

    elif category == "task_request":
        if burst_pending:
            strategy = "emotion_burst"
        elif overthinker >= 0.6 and random.random() < 0.15:
            strategy = "over_associate"
        elif rambler >= 0.5 and random.random() < 0.12:
            strategy = "nonsense"
        elif contradict_prone >= 0.5 and random.random() < contradict_prone:
            strategy = "self_contradict"
        elif excuse_prone >= 0.5 and random.random() < excuse_prone:
            strategy = "excuse"
        else:
            strategy = "normal"

    elif category == "questioning":
        if liar >= 0.5 and random.random() < liar:
            strategy = "gaslight"
        elif knowitall >= 0.5 and random.random() < knowitall:
            strategy = "incorrect_correct"
        elif emotion_low:
            strategy = "tsundere_retort"
        else:
            strategy = "defend"

    else:
        last_was_overthink = strategy_history and strategy_history[-1] == "over_associate"
        overthink_chance = overthinker - 0.5
        if last_was_overthink:
            overthink_chance *= 0.5

        if emotion_low:
            overthink_chance = 0.0
            rambler_chance = 0.0
        else:
            rambler_chance = rambler - 0.5

        if uncertain and rambler >= 0.5 and rambler_chance > 0:
            strategy = "nonsense"
        elif emotion >= 0.7 and yandere >= 0.6:
            strategy = "defend"
        elif overthinker >= 0.6 and random.random() < overthink_chance:
            strategy = "over_associate"
        elif perfectionist >= 0.3 and random.random() < 0.08:
            strategy = "sudden_competence"
        elif rambler >= 0.7 and random.random() < rambler_chance:
            strategy = "nonsense"

    return {
        "strategy": strategy,
        "consecutive_same_strategy": consecutive_same,
        "burst_pending": burst_pending,
    }
