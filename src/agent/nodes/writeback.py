from __future__ import annotations

from agent.state import AgentState


def writeback(state: AgentState) -> AgentState:
    strategy = state.get("strategy", "normal")
    history = list(state.get("strategy_history", []))
    history.append(strategy)

    trigger_counters = dict(state.get("trigger_counters", {}))
    trigger = state.get("trigger")
    if trigger:
        trigger_counters[trigger] = trigger_counters.get(trigger, 0) + 1

    if strategy == "emotion_burst":
        trigger_counters = {}

    emotion = state.get("emotion", 0.0)
    defect_mode = state.get("defect_mode", "none")
    total_triggers = sum(trigger_counters.values())

    user_input = state.get("user_input", "")
    response = state.get("response", "")

    conversation_history = list(state.get("conversation_history", []))
    memory_enabled = state.get("memory_enabled", False)

    if memory_enabled and user_input and response:
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": response})

        max_history = 20
        if len(conversation_history) > max_history:
            conversation_history = conversation_history[-max_history:]

    turn_count = state.get("turn_count", 0) + 1

    context_lines = []
    if conversation_history and memory_enabled:
        recent = conversation_history[-6:]
        for entry in recent:
            role_short = "U" if entry["role"] == "user" else "A"
            ctx = entry["content"][:40].replace("\n", " ")
            context_lines.append(f"[{role_short}] {ctx}")

    history_summary = (
        f"turn={turn_count}; last_strategy={strategy}; defect_mode={defect_mode}; "
        f"emotion={emotion:.2f}; trigger={trigger or 'none'}; "
        f"total_triggers={total_triggers}; context={{{' '.join(context_lines)}}}"
    )

    result: AgentState = {
        "strategy_history": history,
        "trigger_counters": trigger_counters,
        "history_summary": history_summary,
        "burst_pending": False,
        "conversation_history": conversation_history,
        "turn_count": turn_count,
    }

    if "system_prompt" in state:
        result["system_prompt"] = state["system_prompt"]

    return result
