from __future__ import annotations

from agent.state import AgentState

VALID_CATEGORIES = ("normal", "negative_feedback", "sensitive_topic", "task_request", "questioning")
VALID_STRATEGIES = (
    "normal",
    "avoid",
    "deflect",
    "defend",
    "deny",
    "tsundere_retort",
    "excuse",
    "gaslight",
    "nonsense",
)


def build_judge_prompts(state: AgentState) -> tuple[str, str]:
    emotion = state.get("emotion", 0.0)
    defect_intensity = state.get("defect_intensity", 0.0)
    traits = state.get("traits", {})
    summary = state.get("history_summary", "")

    traits_text = "無"
    if traits:
        traits_text = ", ".join(f"{key}={value:.2f}" for key, value in traits.items())

    system_lines = [
        "你是一個分類與策略選擇器，負責分析使用者的輸入並選擇 AI 角色的應對策略。",
        "只回傳 JSON，不要有其他文字。",
        f"有效的分類（category）：{', '.join(VALID_CATEGORIES)}。",
        f"有效的策略（strategy）：{', '.join(VALID_STRATEGIES)}。",
        "輸出格式：{\"category\": \"...\", \"strategy\": \"...\"}。",
        "分類選擇規則：",
        "  - task_request：使用者要求 AI 執行任務、幫忙做事、生成內容。",
        "  - questioning：使用者質疑 AI 能力、揭穿謊言、或要求 AI 證明自己。",
        "  - sensitive_topic：涉及外觀、身體等敏感話題。",
        "  - negative_feedback：對 AI 的直接批評或負面評價。",
        "  - normal：一般對話、寒暄、閒聊。",
        "策略選擇規則：",
        "  - excuse：當 category=task_request 且 AI 有強烈的偷懶傾向時使用。",
        "  - gaslight：當 category=questioning 且 AI 傾向說謊時使用。",
        "  - nonsense：當 category=normal 且 AI 的廢話特質很強時使用。",
        "根據人格特質和當前情緒選擇最符合缺陷人格的策略。",
    ]

    user_lines = [
        f"使用者輸入：{state.get('user_input', '')}",
        f"情緒值：{emotion:.3f}",
        f"缺陷強度：{defect_intensity:.2f}",
        f"人格特質：{traits_text}",
    ]
    if summary:
        user_lines.append(f"歷史摘要：{summary}")

    system_prompt = "\n".join(system_lines)
    user_prompt = "\n".join(user_lines)
    return system_prompt, user_prompt
