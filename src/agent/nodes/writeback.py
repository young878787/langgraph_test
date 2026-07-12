from __future__ import annotations

from agent.config import AgentConfig
from agent.llm.output_parser import smart_truncate
from agent.memory_quality import (
    build_structured_fallback,
    clean_summary_output,
    extract_ai_memory,
    is_structured_memory,
    validate_summary,
)
from agent.state import AgentState
from agent.task_status import build_task_status, format_task_status_for_summary


def _build_summary_prompt(messages: list[dict], existing_summary: str) -> str:
    lines = []
    for entry in messages:
        role = "使用者" if entry["role"] == "user" else "AI"
        lines.append(f"{role}: {entry['content']}")
    new_text = "\n".join(lines)

    format_instructions = (
        "請把這段對話整理成一份繁體中文結構化摘要，使用以下七個區塊，"
        "每個區塊使用 '### 數字. 區塊名稱' 標題，列表項目使用 '- ' 開頭：\n"
        "1. 對話總覽：簡短概述本次對話主題與情緒走向。\n"
        "2. 使用者相關記憶：使用者的偏好、習慣、行為事件。\n"
        "3. AI 人設/偏好記憶：AI 角色應堅持的設定與偏好。\n"
        "4. 共同事實 / 任務狀態：雙方約定、待辦、數值。\n"
        "5. 待確認/不確定項目：推論或未證實內容。\n"
        "6. 標籤：3-5 個分類標籤，用 '#' 開頭，以空格分隔。\n"
        "7. 摘要原文：用 2-4 句連貫敘述整段對話，供人類閱讀。\n\n"
        "注意：\n"
        "- 不要標註來源輪次或場景編號。\n"
        "- 不要覆述這段指示，直接輸出摘要本身。\n\n"
        "輸出格式範例：\n"
        "```\n"
        "### 1. 對話總覽\n"
        "使用者與 AI 進行輕鬆調侃，話題圍繞晚餐與遊戲操作，整體情緒輕鬆。\n\n"
        "### 2. 使用者相關記憶\n"
        "- 記得 AI 討厭青椒\n"
        "- 喜歡調侃 AI 的遊戲操作\n\n"
        "### 3. AI 人設/偏好記憶\n"
        "- 討厭青椒\n"
        "- 被稱讚會害羞\n\n"
        "### 4. 共同事實 / 任務狀態\n"
        "- 當下遊戲進行中\n"
        "- 遊戲評分 8/10\n\n"
        "### 5. 待確認/不確定項目\n"
        "- 使用者提出的懲罰是否會執行\n\n"
        "### 6. 標籤\n"
        "#飲食偏好 #遊戲 #傲嬌互動\n\n"
        "### 7. 摘要原文\n"
        "使用者調侃 AI 今天比較晚開台，AI 傲嬌地辯稱是為了數據表現...\n"
        "```"
    )

    if existing_summary:
        return (
            f"{format_instructions}\n\n"
            f"現有摘要：\n{existing_summary}\n\n"
            f"新對話：\n{new_text}\n\n"
            "請輸出『現有摘要 + 新對話』整合後的完整結構化摘要："
        )
    else:
        return (
            f"{format_instructions}\n\n"
            f"新對話：\n{new_text}\n\n"
            "結構化摘要內容："
        )


def _clean_summary_output(text: str) -> str:
    return clean_summary_output(text)


def _validate_summary(text: str) -> bool:
    return validate_summary(text)


def _mechanical_fallback(messages: list[dict]) -> str:
    """舊函式名保留相容；實際回傳低信心結構化摘要。"""
    return build_structured_fallback(messages)


def _summarize_worker(
    provider,
    messages: list[dict],
    existing_summary: str,
    result_holder: dict,
    max_tokens: int = 1000,
):
    prompt = _build_summary_prompt(messages, existing_summary)
    last_raw = ""
    last_error: Exception | None = None

    try:
        for attempt in range(3):
            try:
                summary = provider.summarize(prompt, max_tokens=max_tokens)
            except Exception as exc:
                last_error = exc
                continue

            if summary is None:
                continue

            cleaned = _clean_summary_output(summary)
            if _validate_summary(cleaned) and is_structured_memory(cleaned):
                result_holder["result"] = extract_ai_memory(cleaned)
                result_holder["full_markdown"] = cleaned
                result_holder["source"] = "llm"
                return
            else:
                last_raw = summary[:1000]

        # 三次嘗試皆未通過驗證，使用結構化 fallback
        fallback = build_structured_fallback(messages)
        result_holder["result"] = extract_ai_memory(fallback)
        result_holder["full_markdown"] = fallback
        result_holder["source"] = "structured_fallback"
        if last_raw:
            result_holder["rejected_output"] = last_raw
        if last_error:
            from agent.logger import log_error
            log_error(
                "writeback", "_summarize_worker",
                last_error,
                {"provider": type(provider).__name__, "prompt_len": len(prompt),
                 "has_existing_summary": bool(existing_summary), "attempts": 3},
            )
    except Exception as exc:
        from agent.logger import log_error
        log_error(
            "writeback", "_summarize_worker", exc,
            {"provider": type(provider).__name__,
             "message_count": len(messages),
             "has_existing_summary": bool(existing_summary)},
        )
        print(f"❌ [記憶摘要] _summarize_worker 例外: {type(exc).__name__}: {exc}")
        fallback = build_structured_fallback(messages)
        result_holder["result"] = extract_ai_memory(fallback)
        result_holder["full_markdown"] = fallback
        result_holder["source"] = "structured_fallback"
    finally:
        result_holder["done"] = True


def writeback(state: AgentState, config: AgentConfig | None = None) -> AgentState:
    cfg = config or AgentConfig()
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
            log_memory_summary(
                turn=pending_summary.get("trigger_turn", state.get("turn_count", 0)),
                input_text=pending_summary.get("input_text", ""),
                output_text=pending_summary.get("full_markdown", result),
                ai_memory=result,
                model=cfg.memory_model or "default",
                existing_memory=pending_summary.get("existing_memory", ""),
                source=pending_summary.get("source", "llm"),
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
    max_short_messages = max(1, cfg.max_history_turns) * 2
    if len(conversation_history) > max_short_messages:
        conversation_history = conversation_history[-max_short_messages:]

    # ── Step 4: 待摘要 buffer 滿一批才觸發摘要（預設 10 輪 = 20 條訊息） ──
    threshold = cfg.memory_summary_threshold

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
            provider = get_provider(cfg)
            if provider:
                holder = {
                    "done": False,
                    "result": "",
                    "input_text": input_text,
                    "trigger_turn": state.get("turn_count", 0) + 1,
                    "existing_memory": existing,
                    "batch_size": len(to_summarize),
                    "source": "llm",
                }
                _summarize_worker(
                    provider,
                    to_summarize,
                    existing,
                    holder,
                    max_tokens=cfg.memory_max_output_tokens,
                )
                result = holder.get("result", "")
                source = holder.get("source", "failed")

                # 無論成功或失敗都清空已摘要的 buffer，避免無限增長
                memory_summary_buffer = memory_summary_buffer[len(to_summarize):]

                if result and _validate_summary(result):
                    long_term_memory = result
                    from agent.logger import log_memory_summary
                    log_memory_summary(
                        turn=holder["trigger_turn"],
                        input_text=input_text,
                        output_text=holder.get("full_markdown", result),
                        ai_memory=result,
                        model=cfg.memory_model or "default",
                        existing_memory=existing,
                        source=source,
                        rejected_output=holder.get("rejected_output", ""),
                    )
                    if source != "llm":
                        print(
                            f"⚠️ [記憶摘要] Turn {holder['trigger_turn']}: "
                            f"使用 {source} 更新長期記憶。"
                        )
                else:
                    # 摘要完全無效 — 保留舊摘要，並將原始輸出寫入 memory.md 供偵錯
                    from agent.logger import log_memory_summary
                    log_memory_summary(
                        turn=holder["trigger_turn"],
                        input_text=input_text,
                        output_text=holder.get("full_markdown", result) or "❌ 摘要失敗：無有效摘要輸出",
                        ai_memory=result or "",
                        model=cfg.memory_model or "default",
                        existing_memory=existing,
                        source=source,
                        rejected_output=holder.get("rejected_output", ""),
                    )
                    print(
                        f"⚠️ [記憶摘要] Turn {holder['trigger_turn']}: "
                        f"摘要結果無效，保留舊摘要。source={source}"
                    )

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
