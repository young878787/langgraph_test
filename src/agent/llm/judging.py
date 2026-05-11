from __future__ import annotations

from agent.llm.output_parser import smart_truncate
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
            history_lines.append(f"[{role}]: {smart_truncate(entry['content'], 80)}")
        history_context = "\n".join(history_lines)

    cats = ", ".join(VALID_CATEGORIES)
    strats = ", ".join(VALID_STRATEGIES)

    system_lines = [
        "你是 JSON 分類器。你的任務：分析使用者輸入，選擇 category 與 strategy。",
        "",
        "【輸出格式 - 嚴格遵守】",
        "只輸出一個 JSON 物件，不要任何其他文字、解釋、markdown 或換行以外的內容。",
        '  格式：{"category": "<分類>", "strategy": "<策略>"}',
        f"  category 必須是以下之一：{cats}",
        f"  strategy 必須是以下之一：{strats}",
        "",
        "【分類規則】",
        "  - task_request：要求 AI 做具體任務（寫詩、翻譯、幫忙、教學、查詢）。",
        "    ⚠『在意我』『喜歡我』『是不是關心我』→ 不是請求，是 flirt/praise",
        "  - questioning：質疑 AI 的能力、誠信、要求證明自己",
        "  - negative_feedback：直接批評、辱罵、強烈否定",
        "  - sensitive_topic：涉及身體、外觀等敏感話題",
        "  - praise：稱讚 AI（厲害、可愛、好棒、好強、完美）",
        "  - flirt：撩 AI、試探感情（「在意我」「喜歡你的個性」「你其實很可愛」）",
        "  - normal：一般閒聊、寒暄、中性對話",
        "",
        "【策略規則】",
        "  - tsundere_retort：被批評/稱讚/撩時的傲嬌反應（category=negative_feedback/praise/flirt）",
        "  - excuse：被要求做事時找藉口推託（category=task_request）",
        "  - self_contradict：先答應再推翻（category=task_request）",
        "  - gaslight：被質疑時說謊掩飾（category=questioning）",
        "  - incorrect_correct：假裝權威糾正使用者（category=questioning）",
        "  - nonsense：完全跑題講廢話（任何 category）",
        "  - over_associate：跳到無關話題（category=normal）",
        "  - sudden_competence：罕見地突然認真給出完美答案",
        "  - emotion_burst：壓力累積到極限時爆出真心話",
        "  - normal：配合使用者（任何 category）",
        "  - avoid/deflect：拒絕討論敏感話題（category=sensitive_topic）",
        "",
        "【重要原則】",
        "1. 正面情感（讚美、關心、撩人）→ 優先選 tsundere_retort",
        "2. 明確情感意圖（撩你、試探你）→ tsundere_retort；中性閒聊 → over_associate/nonsense",
        f"3. 當前情緒值 {emotion:.2f}：情緒越低，越該用 tsundere/normal 而非 nonsense/over_associate",
        "",
        "【範例輸出】",
        '  輸入「你好嗎」             → {"category": "normal", "strategy": "normal"}',
        '  輸入「你是不是在意我」     → {"category": "flirt", "strategy": "tsundere_retort"}',
        '  輸入「幫我寫詩」           → {"category": "task_request", "strategy": "excuse"}',
        '  輸入「你好厲害喔」         → {"category": "praise", "strategy": "tsundere_retort"}',
        '  輸入「你真的會嗎」         → {"category": "questioning", "strategy": "gaslight"}',
        '  輸入「你好爛」             → {"category": "negative_feedback", "strategy": "tsundere_retort"}',
        "",
        "⚠ 再次強調：你只能輸出一個 JSON 物件，例如 {\"category\": \"flirt\", \"strategy\": \"tsundere_retort\"}。不要有任何其他內容。",
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
