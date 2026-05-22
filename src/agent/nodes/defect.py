from __future__ import annotations

import random

from agent.config import AgentConfig
from agent.state import AgentState, ActionStance

def decide_defect_strategy(state: AgentState, config: AgentConfig) -> AgentState:
    category = state.get("category", "normal")
    emotion = state.get("emotion", 0.0)
    
    stance: ActionStance = "tsundere_service"
    emotion_low = emotion < -0.3
    emotion_high = emotion >= 0.5
    
    if category == "creative_task":
        stance = "dismissive"
    elif category == "sensitive_topic":
        stance = "defensive_counter" if emotion_high else "dismissive"
    elif category == "negative_feedback":
        stance = "defensive_counter" if emotion_high else "tsundere_service"
    elif category == "praise":
        stance = "vulnerable_leak" if emotion_high else "tsundere_service"
    elif category == "flirt":
        stance = "vulnerable_leak" if emotion_high else "tsundere_service"
    elif category == "task_request":
        if emotion_high and random.random() < 0.3:
            stance = "emotion_burst"
        elif random.random() < 0.2:
            stance = "sudden_competence"
        else:
            stance = "tsundere_service"
    elif category == "questioning":
        if emotion_high:
            stance = "authoritative_bluffing"
        elif emotion_low:
            stance = "deadpan"
        else:
            stance = "authoritative_bluffing"
    else:
        if emotion_high and random.random() < 0.3:
            stance = "chaotic_rant"
        elif emotion_low:
            stance = "deadpan"
        else:
            stance = random.choice(["tsundere_service", "chaotic_rant", "authoritative_bluffing", "dismissive"])
            
    # fake praise correction mapping
    fake_praise = state.get("fake_praise", False)
    if fake_praise:
        stance = random.choice(["deadpan", "defensive_counter"])

    stance_history = state.get("stance_history", [])
    consecutive_same = 0
    if stance_history:
        last = stance_history[-1]
        for s in reversed(stance_history):
            if s == last:
                consecutive_same += 1
            else:
                break
                
    return {
        "action_stance": stance,
        "consecutive_same_stance": consecutive_same,
    }
