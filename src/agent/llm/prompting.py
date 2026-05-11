from __future__ import annotations

from typing import List

from agent.llm.output_parser import smart_truncate
from agent.state import AgentState, STRATEGY_LABELS, STRATEGY_DESCRIPTIONS
from agent.llm.vocab import sample_vocab_palette, sample_tone_tweak


def build_prompts(state: AgentState) -> tuple[str, str]:
    strategy = state.get("strategy", "normal")
    tone_hints = state.get("tone_hints", "")
    summary = state.get("history_summary", "")
    emotion = state.get("emotion", 0.0)
    traits = state.get("traits", {})
    tsundere_level = traits.get("tsundere", 0.0)
    memory_enabled = state.get("memory_enabled", False)
    reasoning_model = state.get("reasoning_model", False)

    strategy_label = STRATEGY_LABELS.get(strategy, strategy)
    strategy_desc = STRATEGY_DESCRIPTIONS.get(strategy, "")

    system_lines = [
        f"你是超級傲嬌 AI 助手，嘴硬心軟、死不認輸。當前策略：{strategy_label}（{strategy_desc}）。",
        f"情緒值 {emotion:.2f}（-1 冷靜 ~ +1 激動）。用繁體中文，禁止說「抱歉」「不好意思」。",
    ]

    if tsundere_level >= 0.7:
        system_lines.append("想幫忙也要先拒絕才勉強答應，用反話掩飾真心。被稱讚要害羞否認。")

    vocab_palette = sample_vocab_palette(emotion)
    system_lines.append(vocab_palette)

    tweak = sample_tone_tweak(emotion)
    system_lines.append(f"【心情】{tweak}")

    system_lines.append(f"語氣指導：{tone_hints}")

    response_length = state.get("response_length", "medium")
    if response_length == "short":
        system_lines.append("【字數上限】1-2句。每句≤20字。像傳訊息秒回，一句打死不廢話。")
    elif response_length == "long":
        system_lines.append("【字數上限】4-6句。每句≤15字。句句乾淨不灌水。")
    elif response_length == "long_long":
        system_lines.append("【字數上限】6-8句。每句≤15字。可鋪陳但句句有事。")
    else:
        system_lines.append("【字數上限】2-3句。每句≤15字。像傳訊息般直接，能一句絕不拆兩句。")

    system_lines.extend([
        "直接輸出最終回應，禁止思考過程、Markdown 列表、*動作描述*。",
        "禁止照抄範例句，每回合語氣用詞需有變化。",
    ])
    if reasoning_model:
        system_lines.append("可用 <think>...</think> 標籤推理，標籤外為最終回應。")
    else:
        system_lines.append("禁止使用 <think> 標籤。")

    if memory_enabled and summary:
        system_lines.append(f"狀態摘要：{summary}")

    long_term = state.get("long_term_memory", "")
    if memory_enabled and long_term:
        system_lines.append(f"長期記憶：{long_term}")

    if memory_enabled:
        conversation_history = state.get("conversation_history", [])
        if conversation_history:
            lines = ["【最近對話】"]
            for entry in conversation_history[-6:]:
                role = "使用者" if entry["role"] == "user" else "傲嬌AI"
                truncated = smart_truncate(entry["content"], 80)
                lines.append(f"{role}: {truncated}")
            lines.append("---")
            system_lines.append("\n".join(lines))

    system_prompt = "\n".join(system_lines)
    user_prompt = state.get("user_input", "")
    return system_prompt, user_prompt


def build_memory_context(state: AgentState) -> str:
    conversation_history = state.get("conversation_history", [])
    if not conversation_history:
        return ""

    lines = ["【先前對話歷史】"]
    for entry in conversation_history[-8:]:
        role = "使用者" if entry["role"] == "user" else "傲嬌AI"
        truncated = smart_truncate(entry["content"], 120)
        lines.append(f"{role}: {truncated}")
    lines.append("---")
    return "\n".join(lines)


def build_contents_for_gemini(
    system_prompt: str,
    conversation_history: List[dict],
    current_user_input: str,
) -> list:
    from google.genai import types

    contents = []

    for entry in conversation_history:
        role = "user" if entry["role"] == "user" else "model"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part(text=entry["content"])],
            )
        )

    contents.append(
        types.Content(
            role="user",
            parts=[types.Part(text=current_user_input)],
        )
    )

    return contents
