from __future__ import annotations

from agent.state import AgentState

VALID_CATEGORIES = (
    "normal",
    "negative_feedback",
    "sensitive_topic",
    "task_request",
    "questioning",
    "praise",
    "flirt",
)
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
    "self_contradict",
    "over_associate",
    "incorrect_correct",
    "sudden_competence",
    "emotion_burst",
)


def build_judge_prompts(state: AgentState) -> tuple[str, str]:
    emotion = state.get("emotion", 0.0)
    defect_intensity = state.get("defect_intensity", 0.0)
    traits = state.get("traits", {})
    conversation_history = state.get("conversation_history", [])

    traits_text = "無"
    if traits:
        traits_text = ", ".join(f"{key}={value:.2f}" for key, value in traits.items())

    history_context = ""
    if conversation_history:
        recent = conversation_history[-4:]
        history_lines = []
        for entry in recent:
            role = "使用者" if entry["role"] == "user" else "AI(傲嬌)"
            history_lines.append(f"[{role}]: {entry['content'][:60]}")
        history_context = "\n".join(history_lines)

    system_lines = [
        "你是一個分類與策略選擇器，負責分析使用者的輸入並選擇 AI 角色的應對策略。",
        "只回傳 JSON，不要有任何其他文字。",
        f"有效的分類（category）：{', '.join(VALID_CATEGORIES)}。",
        f"有效的策略（strategy）：{', '.join(VALID_STRATEGIES)}。",
        '輸出格式：{"category": "...", "strategy": "..."}。',
        "",
        "⸻ 分類規則 ⸻",
        "  - task_request：使用者要求 AI 做具體任務（寫詩、翻譯、幫忙、教學、查詢等）。",
        "    ⚠ 注意：『在意我』『喜歡我』『是不是關心我』——這些不是請求，是 flirt/praise。",
        "  - questioning：使用者質疑 AI 的能力、誠信、或要求 AI 證明自己。",
        "  - negative_feedback：直接批評、辱罵、或強烈否定 AI。",
        "  - sensitive_topic：涉及身體、外觀等敏感話題。",
        "  - praise：使用者稱讚 AI、說 AI 厲害/可愛/好棒。",
        "  - flirt：使用者撩 AI，例如『是不是在意我』『你其實很可愛』『喜歡你的個性』。",
        "  - normal：一般閒聊、寒暄、不帶強烈意圖的對話。",
        "",
        "⸻ 策略規則 ⸻",
        "  - tsundere_retort：被批評或稱讚時的傲嬌反擊/害羞（category=negative_feedback/praise/flirt）。",
        "  - excuse：被要求做事時的推託（category=task_request）。",
        "  - self_contradict：被要求做事時先答應再推翻（category=task_request）。",
        "  - gaslight：被質疑時說謊掩飾（category=questioning）。",
        "  - incorrect_correct：被質疑時假裝權威糾正使用者（category=questioning）。",
        "  - nonsense：完全跑題講廢話（任何 category 都有可能）。",
        "  - over_associate：從關鍵字跳到無關話題（category=normal 時）。",
        "  - sudden_competence：罕見地突然認真給出完美答案。",
        "  - emotion_burst：壓力累積到極限時爆出真心話。",
        "  - normal：配合使用者（category=normal 或不好判斷時）。",
        "  - avoid/deflect：拒絕討論敏感話題（category=sensitive_topic）。",
        "",
        "⸻ 重要判斷原則 ⸻",
        "1. 如果使用者表達正面情感（讚美、關心、撩人），優先選 tsundere_retort，而非 over_associate/nonsense。",
        "2. 如果上一輪對話氛圍已經很親密，繼續保持 tsundere 的風格，不要突然離題。",
        "3. 如果使用者的話有明確的情感意圖（撩你、試探你），用 tsundere_retort 接招；如果是中性閒聊，可以用 over_associate/nonsense。",
        f"4. 當前情緒值 {emotion:.2f}：情緒越低，越該用 tsundere/normal 而非哲學離題。",
    ]

    user_lines = [
        f"上一段對話：\n{history_context}" if history_context else "（尚無對話歷史）",
        f"使用者現在說：{state.get('user_input', '')}",
        f"當前情緒值：{emotion:.3f}（-1=冷靜, 1=激動）",
        f"缺陷強度：{defect_intensity:.2f}",
        f"人格特質：{traits_text}",
    ]

    system_prompt = "\n".join(system_lines)
    user_prompt = "\n\n".join(user_lines)
    return system_prompt, user_prompt
