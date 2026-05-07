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

    emotion = state.get("emotion", 0.0)
    history_summary = f"last_strategy={strategy}; emotion={emotion:.2f}; trigger={trigger or 'none'}"

    # 保留 system_prompt 和其他欄位
    result = {
        "strategy_history": history,
        "trigger_counters": trigger_counters,
        "history_summary": history_summary,
    }
    
    # 確保 system_prompt 被保留
    if "system_prompt" in state:
        result["system_prompt"] = state["system_prompt"]
    
    return result
