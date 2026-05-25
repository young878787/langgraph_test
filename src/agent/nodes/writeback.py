from __future__ import annotations

from agent.llm.output_parser import smart_truncate
from agent.state import AgentState
from agent.task_status import build_task_status, format_task_status_for_summary


def _build_summary_prompt(messages: list[dict], existing_summary: str) -> str:
    lines = []
    for entry in messages:
        role = "使用者" if entry["role"] == "user" else "AI"
        lines.append(f"{role}: {entry['content']}")
    new_text = "\n".join(lines)

    base_instructions = (
        "【摘要萃取準則】\n"
        "1. **意圖區分**：明確區分「誰提議/陳述」與「對方的實際態度（如：拒絕、敷衍、迴避、條件性接受）」，絕不可將單方面提議誤認為雙方共識。\n"
        "2. **狀態轉折**：保留對話中的情緒變化或話題切換過程，而非只記錄最終結果。\n"
        "3. **客觀陳述**：如遇混亂或無意義閒扯，僅需簡述「雙方進行了無特定主題的閒聊/互相吐槽」，避免過度腦補不存在的邏輯。\n"
        "4. **事實提煉**：優先保留對話中出現的具體偏好、事件或承諾。\n"
    )

    if existing_summary:
        return (
            "請將以下新對話的互動過程，精準合併到現有摘要中（繁體中文，≤350字）。\n"
            f"{base_instructions}\n"
            "只輸出摘要內容，不要加標題或前綴。\n\n"
            f"現有摘要：{existing_summary}\n\n"
            f"新對話：\n{new_text}\n\n"
            "摘要內容："
        )
    else:
        return (
            "請將以下對話片段濃縮成簡短摘要（繁體中文，≤250字）。\n"
            f"{base_instructions}\n"
            "只輸出摘要內容，不要加標題或前綴。\n\n"
            f"{new_text}\n\n"
            "摘要內容："
        )

def _build_entity_prompt(messages: list[dict]) -> str:
    lines = []
    for entry in messages:
        role = "使用者" if entry["role"] == "user" else "AI"
        lines.append(f"{role}: {entry['content']}")
    new_text = "\n".join(lines)

    return (
        "請從以下對話中，提取出與「世界狀態(World State)」相關的具體實體記憶。\n"
        "世界狀態包含：直播環節（如正在玩的遊戲與關卡進度）、聊天室與實況主的共同約定、內梗（Running jokes）、剛發生的具體事件或強烈的情緒轉折。\n"
        "必須盡可能詳實記錄有意義的上下文，保留足夠的細節，不要過度省略。\n"
        "若無任何有意義的資訊，請直接回答「無新記憶」。\n\n"
        "請以條列式輸出（不要包含前綴）：\n"
        "【世界狀態】：...\n\n"
        f"新對話：\n{new_text}\n\n"
        "提取結果："
    )


def _clean_summary_output(text: str) -> str:
    cleaned = text.strip()
    prefixes = (
        "輸出更新後的完整摘要：",
        "輸出更新後的完整摘要:",
        "輸出摘要：",
        "輸出摘要:",
        "摘要內容：",
        "摘要內容:",
    )
    changed = True
    while changed:
        changed = False
        cleaned = cleaned.strip()
        for prefix in prefixes:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                changed = True
    return cleaned


def _summarize_worker(provider, messages: list[dict], existing_summary: str, result_holder: dict):
    try:
        prompt = _build_summary_prompt(messages, existing_summary)
        summary = provider.summarize(prompt)
        result_holder["result"] = _clean_summary_output(summary or "")
        
        # 實體記憶萃取
        entity_prompt = _build_entity_prompt(messages)
        entities = provider.summarize(entity_prompt)
        if entities and "無新記憶" not in entities:
            from agent.logger import WORLD_STATE_MD
            try:
                import re
                world_match = re.search(r"【世界狀態】[：:](.*?)$", entities, re.DOTALL)
                if world_match and world_match.group(1).strip():
                    with open(WORLD_STATE_MD, "a", encoding="utf-8") as f:
                        f.write(f"- {world_match.group(1).strip()}\n")
            except Exception as e:
                print(f"寫入實體記憶失敗: {e}")
                
    except Exception:
        result_holder["result"] = ""
    finally:
        result_holder["done"] = True


def writeback(state: AgentState) -> AgentState:
    stance = state.get("action_stance", "tsundere_service")
    stance_history = list(state.get("stance_history", []))
    stance_history.append(stance)
    response_flow = state.get("response_flow", "direct_answer")
    response_flow_history = list(state.get("response_flow_history", []))
    response_flow_history.append(response_flow)

    trigger_counters = dict(state.get("trigger_counters", {}))
    trigger = state.get("trigger")
    if trigger:
        trigger_counters[trigger] = trigger_counters.get(trigger, 0) + 1

    if stance == "emotion_burst":
        trigger_counters = {}

    emotion = state.get("emotion", 0.0)
    total_triggers = sum(trigger_counters.values())

    user_input = state.get("user_input", "")
    response = state.get("response", "")

    conversation_history = list(state.get("conversation_history", []))
    memory_summary_buffer = list(state.get("memory_summary_buffer", []))
    memory_enabled = state.get("memory_enabled", False)
    long_term_memory = state.get("long_term_memory", "")

    # ── Step 1: 套用舊版流程可能留下的 pending 摘要 ──
    pending_summary = state.get("pending_summary", {})
    if pending_summary and pending_summary.get("done"):
        result = pending_summary.get("result", "")
        if result:
            long_term_memory = result
            batch_size = pending_summary.get("batch_size", 0)
            if batch_size > 0:
                memory_summary_buffer = memory_summary_buffer[batch_size:]
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
        new_messages = [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": response},
        ]
        conversation_history.extend(new_messages)
        memory_summary_buffer.extend(new_messages)

    # ── Step 3: 短期上下文只保留最近 N 輪，長期記憶由 buffer 批次摘要 ──
    from agent.config import AgentConfig
    _cfg = AgentConfig()
    max_short_messages = max(1, _cfg.max_history_turns) * 2
    if len(conversation_history) > max_short_messages:
        conversation_history = conversation_history[-max_short_messages:]

    # ── Step 4: 待摘要 buffer 滿一批才觸發摘要（預設 10 輪 = 20 條訊息） ──
    threshold = _cfg.memory_summary_threshold

    if memory_enabled and len(memory_summary_buffer) >= threshold:
        pending_active = bool(pending_summary) and not pending_summary.get("done")
        to_summarize = memory_summary_buffer[:threshold]

        if not pending_active:
            existing = long_term_memory if long_term_memory else ""

            # 構建輸入文本供日誌記錄
            input_lines = []
            for entry in to_summarize:
                role = "使用者" if entry["role"] == "user" else "AI"
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
                    "batch_size": len(to_summarize),
                }
                _summarize_worker(provider, to_summarize, existing, holder)
                result = holder.get("result", "")
                if result:
                    long_term_memory = result
                    memory_summary_buffer = memory_summary_buffer[len(to_summarize):]

                    from agent.logger import log_memory_summary

                    log_memory_summary(
                        turn=holder["trigger_turn"],
                        input_text=input_text,
                        output_text=result,
                        model=_cfg.memory_model or "default",
                        existing_memory=existing,
                    )
                else:
                    pending_summary = {}

    # ── Step 5: 生成輕量狀態摘要（純狀態追蹤，不含對話內容） ──
    turn_count = state.get("turn_count", 0) + 1
    last_task_status = build_task_status(state, turn_count)

    last_topic = ""
    if conversation_history and memory_enabled:
        for entry in reversed(conversation_history):
            if entry["role"] == "user":
                last_topic = smart_truncate(entry["content"], 60).replace("\n", " ")
                break

    status_flags = []
    if stance == "authoritative_bluffing":
        status_flags.append("bluffing")
    if stance == "emotion_burst":
        status_flags.append("burst")
    task_status_summary = format_task_status_for_summary(last_task_status)
    if task_status_summary:
        status_flags.append(task_status_summary)
    if last_topic:
        status_flags.append(f"topic:{last_topic}")

    history_summary = (
        f"turn={turn_count}; stance={stance}; "
        f"flow={response_flow}; "
        f"emotion={emotion:.2f}; trigger={trigger or 'none'}; "
        f"total_triggers={total_triggers}"
    )
    if status_flags:
        history_summary += "; " + "; ".join(status_flags)

    # ── Step 6: Performance Mapper (Live2D / TTS) ──
    resolved_emotion = state.get("resolved_emotion", {})
    character_state = state.get("character_state", {})
    perf_output = dict(state.get("performance_output", {}))
    
    perf_output["live2d"] = {
        "expression": resolved_emotion.get("base", "neutral"),
        "intensity": resolved_emotion.get("intensity", 0.5),
        "eye_contact": 0.8 if character_state.get("confidence", 0.5) > 0.6 else 0.4,
        "blush_level": character_state.get("embarrassment", 0.0)
    }
    
    perf_output["tts"] = {
        "speed": 1.2 if character_state.get("tension", 0.1) > 0.6 else (0.8 if resolved_emotion.get("base") == "sad" else 1.0),
        "pitch": 1.1 if character_state.get("energy", 0.5) > 0.7 else 1.0,
        "volume": 0.8 if character_state.get("confidence", 0.5) < 0.4 else 1.0
    }

    # ── Step 7: 回寫狀態 ──
    result: AgentState = {
        "stance_history": stance_history,
        "response_flow_history": response_flow_history,
        "trigger_counters": trigger_counters,
        "history_summary": history_summary,
        "burst_pending": False,
        "conversation_history": conversation_history,
        "memory_summary_buffer": memory_summary_buffer,
        "turn_count": turn_count,
        "long_term_memory": long_term_memory,
        "pending_summary": pending_summary,
        "last_task_status": last_task_status,
        "performance_output": perf_output,
    }

    if "system_prompt" in state:
        result["system_prompt"] = state["system_prompt"]
    if "provider_history_count" in state:
        result["provider_history_count"] = state["provider_history_count"]
    if "provider_history_preview" in state:
        result["provider_history_preview"] = state["provider_history_preview"]

    return result
