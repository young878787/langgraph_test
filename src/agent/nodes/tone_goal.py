from __future__ import annotations

from agent.state import AgentState, ResponseGoal


def decide_response_goal(state: AgentState) -> ResponseGoal:
    category = state.get("category", "normal")
    event_analysis = state.get("event_analysis", {})
    risk = event_analysis.get("risk", 0.0)
    try:
        risk_value = float(risk)
    except (TypeError, ValueError):
        risk_value = 0.0

    if state.get("fake_praise"):
        return "repair_misunderstanding"
    if category == "farewell":
        return "close_conversation"
    if category in ("creative_task", "sensitive_topic"):
        return "maintain_boundary"
    if category == "negative_feedback":
        if risk_value >= 0.45:
            return "maintain_boundary"
        return "acknowledge_emotion"
    if state.get("sarcasm_possible"):
        return "repair_misunderstanding"
    if category in ("task_request", "questioning"):
        return "answer_user"
    if category in ("praise", "flirt"):
        return "acknowledge_emotion"
    return "continue_banter"
