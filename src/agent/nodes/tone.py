from __future__ import annotations

from agent.config import AgentConfig
from agent.state import AgentState
from agent.nodes.tone_flow import decide_response_flow
from agent.nodes.tone_goal import decide_response_goal
from agent.nodes.tone_performance import (
    build_acting_brief,
    build_expression_projection,
    resolve_vtuber_emotion,
)


def _decide_response_length(
    stance: str,
    category: str,
    response_flow: str,
    resolved_emotion: dict,
) -> str:
    response_length = "medium"
    if stance in ("dismissive", "deadpan") or resolved_emotion.get("style") == "boundary":
        response_length = "short"
    elif stance in ("chaotic_rant", "authoritative_bluffing", "emotion_burst"):
        response_length = "long"
    elif category == "sensitive_topic":
        response_length = "short"

    if response_flow in ("dry_answer", "deadpan_deny", "hard_deflect"):
        response_length = "short"
    elif response_flow in ("spiral_rant", "burst_then_comply", "overhelp_then_deny"):
        response_length = "long"

    return response_length


def _build_tone_hints(
    state: AgentState,
    stance: str,
    emotion: float,
    response_goal: str,
) -> str:
    ambiguous = state.get("ambiguous_flag", False)
    sarcasm_possible = state.get("sarcasm_possible", False)
    hints = "保持自然的實況主語氣。"

    if state.get("fake_praise"):
        return "語氣冷淡、短促反問；不要長篇解釋，也不要把語氣拉得太凶。"

    if sarcasm_possible:
        return "保留一點警覺，用短促吐槽或反問；不要直接認定對方惡意。"

    if response_goal == "maintain_boundary":
        return "語氣清楚、短句、有界線；角色感只能當包裝。"
    if response_goal == "close_conversation":
        return "語氣短促但留一點溫度，不要突然變成任務回答。"

    if ambiguous:
        return "語氣自然，少量保留彈性；不要過度腦補或放大單一關鍵字。"

    if stance == "tsundere_service":
        if emotion > 0.5:
            hints = "傲嬌成分加重，語氣可以再急躁一點。"
        elif emotion < -0.3:
            hints = "傲嬌成分減輕，帶一點不耐煩的冷淡。"

    return hints


def _merge_expression_projection(
    hints: str,
    projection: dict,
    state: AgentState,
    response_goal: str,
) -> str:
    style = projection.get("style", "normal")
    if style == "normal":
        return hints
    if state.get("fake_praise") or state.get("sarcasm_possible"):
        return hints
    if response_goal == "close_conversation":
        return hints
    if response_goal == "maintain_boundary" and style != "boundary":
        return hints

    display = projection.get("display", "")
    tone = projection.get("tone", "")
    avoid = projection.get("avoid", [])
    intensity = projection.get("intensity", 0.5)
    if not display:
        return hints
    projection_hint = f"外顯方式：{display}。"
    if tone:
        projection_hint += f"說話感覺：{tone}。"
    if isinstance(intensity, (int, float)) and not isinstance(intensity, bool):
        if intensity >= 0.8:
            projection_hint += "表現程度：明顯，但不要失控。"
        elif intensity <= 0.3:
            projection_hint += "表現程度：淡淡帶過，不要過度演出。"
    if avoid:
        projection_hint += f"避免：{'、'.join(avoid)}。"
    return f"{hints} {projection_hint}"


def build_tone_strategy(state: AgentState, config: AgentConfig) -> AgentState:
    stance = state.get("action_stance", "tsundere_service")
    emotion = state.get("emotion", 0.0)
    category = state.get("category", "normal")
    response_goal = decide_response_goal(state)
    flow_state = {**state, "response_goal": response_goal}
    response_flow, flow_reason = decide_response_flow(flow_state)

    character_state = state.get("character_state", {})
    resolved_emotion = resolve_vtuber_emotion(character_state)
    acting_brief = build_acting_brief(resolved_emotion)
    expression_projection = build_expression_projection(acting_brief, resolved_emotion)
    response_length = _decide_response_length(
        stance,
        category,
        response_flow,
        resolved_emotion,
    )
    hints = _build_tone_hints(state, stance, emotion, response_goal)
    hints = _merge_expression_projection(hints, expression_projection, state, response_goal)

    return {
        "tone_hints": hints,
        "response_length": response_length,
        "response_goal": response_goal,
        "response_flow": response_flow,
        "flow_reason": f"category={category}, goal={response_goal}, emotion={emotion:.2f}; {flow_reason}",
        "resolved_emotion": resolved_emotion,
        "acting_brief": acting_brief,
        "expression_projection": expression_projection,
    }
