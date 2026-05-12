from __future__ import annotations

import threading

from agent.llm.output_parser import smart_truncate
from agent.state import AgentState


def _build_summary_prompt(messages: list[dict], existing_summary: str) -> str:
    lines = []
    for entry in messages:
        role = "使用者" if entry["role"] == "user" else "AI"
        lines.append(f"{role}: {entry['content']}")
    new_text = "\n".join(lines)

    if existing_summary:
        return (
            "請將以下新對話合併到現有摘要中，輸出更新後的摘要（繁體中文，≤300字）。\n\n"
            f"現有摘要：{existing_summary}\n\n"
            f"新對話：\n{new_text}\n\n"
            "輸出更新後的完整摘要："
        )
    else:
        return (
            "請將以下對話片段濃縮成簡短摘要（繁體中文，≤200字），保留關鍵資訊和使用者意圖。\n\n"
            f"{new_text}\n\n"
            "輸出摘要："
        )


def _summarize_worker(provider, messages: list[dict], existing_summary: str, result_holder: dict):
    try:
        prompt = _build_summary_prompt(messages, existing_summary)
        summary = provider.summarize(prompt)
        result_holder["result"] = (summary or "").strip()
    except Exception:
        result_holder["result"] = ""
    finally:
        result_holder["done"] = True


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
    total_triggers = sum(trigger_counters.values())

    user_input = state.get("user_input", "")
    response = state.get("response", "")

    conversation_history = list(state.get("conversation_history", []))
    memory_enabled = state.get("memory_enabled", False)
    long_term_memory = state.get("long_term_memory", "")

    # ── Step 1: 檢查是否有待完成的異步摘要 ──
    pending_summary = state.get("pending_summary", {})
    if pending_summary and pending_summary.get("done"):
        result = pending_summary.get("result", "")
        if result:
            long_term_memory = result
            # 記錄記憶摘要到 logs/memory.md
            from agent.logger import log_memory_summary
            from agent.config import AgentConfig as _ACfg
            _cfg2 = _ACfg()
            log_memory_summary(
                turn=pending_summary.get("trigger_turn", state.get("turn_count", 0)),
                input_text=pending_summary.get("input_text", ""),
                output_text=result,
                model=_cfg2.memory_model or "default",
                existing_memory=pending_summary.get("existing_memory", ""),
            )
        pending_summary = {}

    # ── Step 2: 追加本輪對話 ──
    if memory_enabled and user_input and response:
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": response})

    # ── Step 3: 軟上限截斷（保留最後 60 條，避免記憶體洩漏） ──
    max_soft = 60
    if len(conversation_history) > max_soft:
        conversation_history = conversation_history[-max_soft:]

    # ── Step 4: 閾值觸發異步摘要（15 輪 = 30 條訊息） ──
    from agent.config import AgentConfig
    _cfg = AgentConfig()
    threshold = _cfg.memory_summary_threshold

    if memory_enabled and len(conversation_history) > threshold:
        pending_active = bool(pending_summary) and not pending_summary.get("done")
        overflow_count = len(conversation_history) - threshold
        to_summarize = conversation_history[:overflow_count]
        conversation_history = conversation_history[overflow_count:]

        if not pending_active:
            existing = long_term_memory if long_term_memory else ""

            # 構建輸入文本供日誌記錄
            input_lines = []
            for entry in to_summarize:
                role = "使用者" if entry["role"] == "user" else "傲嬌AI"
                input_lines.append(f"{role}: {entry['content']}")
            input_text = "\n".join(input_lines)

            from agent.llm.providers import get_provider
            provider = get_provider(_cfg)
            if provider:
                holder = {
                    "done": False,
                    "result": "",
                    "input_text": input_text,
                    "trigger_turn": state.get("turn_count", 0) + 1,
                    "existing_memory": existing,
                }
                t = threading.Thread(
                    target=_summarize_worker,
                    args=(provider, to_summarize, existing, holder),
                    daemon=True,
                )
                t.start()
                holder["thread"] = t
                pending_summary = holder

    # ── Step 5: 生成輕量狀態摘要（純狀態追蹤，不含對話內容） ──
    turn_count = state.get("turn_count", 0) + 1

    last_topic = ""
    if conversation_history and memory_enabled:
        for entry in reversed(conversation_history):
            if entry["role"] == "user":
                last_topic = smart_truncate(entry["content"], 60).replace("\n", " ")
                break

    status_flags = []
    if strategy == "gaslight":
        status_flags.append("gaslight")
    if strategy == "emotion_burst":
        status_flags.append("burst")
    if last_topic:
        status_flags.append(f"topic:{last_topic}")

    history_summary = (
        f"turn={turn_count}; strategy={strategy}; "
        f"emotion={emotion:.2f}; trigger={trigger or 'none'}; "
        f"total_triggers={total_triggers}"
    )
    if status_flags:
        history_summary += "; " + "; ".join(status_flags)

    # ── Step 6: 回寫狀態 ──
    result: AgentState = {
        "strategy_history": history,
        "trigger_counters": trigger_counters,
        "history_summary": history_summary,
        "burst_pending": False,
        "conversation_history": conversation_history,
        "turn_count": turn_count,
        "long_term_memory": long_term_memory,
        "pending_summary": pending_summary,
    }

    if "system_prompt" in state:
        result["system_prompt"] = state["system_prompt"]
    if "provider_history_count" in state:
        result["provider_history_count"] = state["provider_history_count"]
    if "provider_history_preview" in state:
        result["provider_history_preview"] = state["provider_history_preview"]

    return result
