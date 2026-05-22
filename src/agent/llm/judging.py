from __future__ import annotations

from agent.llm.output_parser import smart_truncate
from agent.state import AgentState
from agent.task_status import format_task_status_for_prompt

VALID_CATEGORIES = (
    "normal",
    "negative_feedback",
    "sensitive_topic",
    "task_request",
    "creative_task",
    "questioning",
    "praise",
    "flirt",
)

def build_judge_prompts(state: AgentState) -> tuple[str, str]:
    emotion = state.get("emotion", 0.0)
    traits = state.get("traits", {})
    conversation_history = state.get("conversation_history", [])
    task_status = format_task_status_for_prompt(state.get("last_task_status", {}))

    traits_text = "無"
    if traits:
        traits_text = ", ".join(f"{key}={value:.2f}" for key, value in traits.items())

    history_context = ""
    if conversation_history:
        recent = conversation_history[-4:]
        history_lines = []
        for entry in recent:
            role = "使用者" if entry["role"] == "user" else "AI"
            history_lines.append(f"[{role}]: {smart_truncate(entry['content'], 80)}")
        history_context = "\n".join(history_lines)

    cats = ", ".join(VALID_CATEGORIES)

    system_lines = [
        "你是 JSON 分類器。你的任務：分析使用者輸入，選擇 category。",
        "",
        "【輸出格式 - 嚴格遵守】",
        "只輸出一個 JSON 物件，不要任何其他文字、解釋、markdown 或換行以外的內容。",
        '  格式：{"category": "<分類>"}',
        f"  category 必須是以下之一：{cats}",
        "",
        "【分類規則】",
        "  - creative_task：要求 AI 創作（寫詩、寫故事、作曲、翻譯、寫程式、畫畫、寫文案）。",
        "  - task_request：要求 AI 做具體任務（幫忙、教學、查詢、計算、解釋）。",
        "    ⚠ 若涉及創作，請歸類為 creative_task。",
        "    ⚠『在意我』『喜歡我』『是不是關心我』→ 不是請求，是 flirt/praise",
        "  - questioning：質疑 AI 的能力、誠信、要求證明自己",
        "  - negative_feedback：直接批評、辱罵、強烈否定",
        "  - sensitive_topic：涉及身體、外觀等敏感話題",
        "  - praise：稱讚 AI（厲害、可愛、好棒、好強、完美）",
        "    ⚠ 關鍵：判定 praise 前，必須檢查對話歷史中 AI 是否真的做了被稱讚的事。",
        "    若使用者稱讚的內容在對話歷史中不存在，不可歸類為 praise，應歸類為 questioning。",
        "  - flirt：撩 AI、試探感情",
        "  - normal：一般閒聊、寒暄、中性對話",
        "",
        "【範例輸出】",
        '  輸入「你好嗎」             → {"category": "normal"}',
        '  輸入「你是不是在意我」     → {"category": "flirt"}',
        '  輸入「幫我寫詩」           → {"category": "creative_task"}',
        '  輸入「幫我翻譯這段」       → {"category": "creative_task"}',
        '  輸入「1+1等於多少」       → {"category": "task_request"}',
        '  輸入「你好厲害喔」         → {"category": "praise"}',
        '  輸入「你真的會嗎」         → {"category": "questioning"}',
        '  輸入「你好爛」             → {"category": "negative_feedback"}',
        "",
        "⚠ 再次強調：你只能輸出一個 JSON 物件，例如 {\"category\": \"flirt\"}。不要有任何其他內容。",
    ]

    user_lines = [
        f"上一段對話：\n{history_context}" if history_context else "（尚無對話歷史）",
        f"使用者現在說：{state.get('user_input', '')}",
        f"當前情緒值：{emotion:.3f}（-1=冷靜, 1=激動）",
        f"人格特質：{traits_text}",
        f"上一個任務狀態：{task_status or '無'}",
    ]

    system_prompt = "\n".join(system_lines)
    user_prompt = "\n\n".join(user_lines)
    return system_prompt, user_prompt
