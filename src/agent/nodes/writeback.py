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

    history_summary = (
        f"last_strategy={strategy}; defect_mode={defect_mode}; "
        f"emotion={emotion:.2f}; trigger={trigger or 'none'}; "
        f"total_triggers={total_triggers}"
    )

    result = {
        "strategy_history": history,
        "trigger_counters": trigger_counters,
        "history_summary": history_summary,
        "burst_pending": False,
    }

    if "system_prompt" in state:
        result["system_prompt"] = state["system_prompt"]

    return result
