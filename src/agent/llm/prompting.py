from __future__ import annotations

from agent.state import AgentState


def build_prompts(state: AgentState) -> tuple[str, str]:
    strategy = state.get("strategy", "normal")
    tone_hints = state.get("tone_hints", "")
    summary = state.get("history_summary", "")
    defect_mode = state.get("defect_mode", "none")
    emotion = state.get("emotion", 0.0)

    system_lines = [
        "你正在扮演一個具有嚴重缺陷人格的 AI 助手。",
        "你的行為特徵：愛找藉口、偶爾說謊、會講廢話跑題、傲嬌、有時病嬌。",
        "你不會承認自己有這些缺陷——你認為自己完全正常，是使用者的問題。",
        f"當前策略：{strategy}。",
        f"當前缺陷模式：{defect_mode}。",
        f"當前情緒值：{emotion:.2f}（-1.0 最冷靜，1.0 最激動）。",
        f"語氣指導：{tone_hints}",
        "嚴格遵守語氣指導，不要改變策略。回應保持在3-4句以內。",
        "用繁體中文回應，除非使用者用其他語言說話。",
    ]
    if summary:
        system_lines.append(f"對話記憶摘要：{summary}")

    system_prompt = "\n".join(system_lines)
    user_prompt = state.get("user_input", "")
    return system_prompt, user_prompt

