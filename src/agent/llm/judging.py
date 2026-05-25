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
    "farewell",
)

VALID_INTENT_TARGETS = ("assistant", "user", "third_party", "none", "unknown")


def _format_keyword_signals(state: AgentState) -> str:
    signals = state.get("keyword_signals", [])
    if not signals:
        return "無"

    parts = []
    for signal in signals[:8]:
        category = signal.get("category", "unknown")
        trigger = signal.get("trigger", "")
        parts.append(f"{category}:{trigger}")
    omitted = len(signals) - len(parts)
    if omitted > 0:
        parts.append(f"...另 {omitted} 個")
    return "；".join(parts)


def build_judge_prompts(state: AgentState) -> tuple[str, str]:
    emotion = state.get("emotion", 0.0)
    traits = state.get("traits", {})
    conversation_history = state.get("conversation_history", [])
    task_status = format_task_status_for_prompt(state.get("last_task_status", {}))
    keyword_signals = _format_keyword_signals(state)
    keyword_confidence = state.get("keyword_confidence", "none")

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
        "你是 JSON 分類器。你的任務：分析使用者輸入，輸出事件分析 JSON。",
        "",
        "【輸出格式 - 嚴格遵守】",
        "只輸出一個 JSON 物件，不要任何其他文字、解釋、markdown 或換行以外的內容。",
        "格式範例：",
        "{",
        '  "category": "<舊版分類>",',
        '  "event_type": "<事件類型>",',
        '  "subtype": "<子類型，例如 appearance_compliment>",',
        '  "tone": "<觀眾語氣，例如 friendly>",',
        '  "intensity": 0.55,',
        '  "risk": 0.05,',
        '  "relationship_signal": "<closer 或 distant>",',
        '  "ambiguous": false,',
        '  "sarcasm_possible": false,',
        '  "requires_action": false,',
        '  "target": "assistant",',
        '  "state_delta_suggestion": {',
        '    "mood": 0.05,',
        '    "confidence": 0.03,',
        '    "embarrassment": 0.08,',
        '    "tension": 0.01,',
        '    "intimacy": 0.03',
        '  }',
        "}",
        f"  category 必須是以下之一：{cats}",
        "  event_type 建議為：praise, tease, question, concern, command, silence, hostile, boundary, confusion 等。",
        "  ambiguous / sarcasm_possible / requires_action 必須是 boolean。",
        f"  target 必須是以下之一：{', '.join(VALID_INTENT_TARGETS)}",
        "  intensity 與 risk 為 0.0 到 1.0 的浮點數。",
        "  state_delta_suggestion 中的 key 包含 mood, confidence, embarrassment, tension, intimacy 等，數值範圍為 -1.0 到 1.0 (建議微調)。",
        "",
        "【分類規則】",
        "  - 關鍵字只是 evidence，不是最終判決。若關鍵字與完整語境衝突，必須以語境為準。",
        "  - 若一句話同時有多重意圖，請標 ambiguous=true，並選擇最能代表本輪回應義務的 category。",
        "  - 若稱讚語句帶有挖苦、反問、前後矛盾，請標 sarcasm_possible=true，通常不要歸類為 praise。",
        "  - creative_task：要求 AI 創作（寫詩、寫故事、寫程式、畫畫）。",
        "  - task_request：要求 AI 做具體任務（幫忙、教學、查詢）。",
        "    ⚠『在意我』『喜歡我』『是不是關心我』→ 不是請求，是 flirt/praise",
        "  - questioning：質疑 AI 的能力、誠信。",
        "  - negative_feedback：直接批評、辱罵 (對應 hostile/boundary)。",
        "  - sensitive_topic：涉及身體、外觀等敏感話題 (對應 boundary/concern)。",
        "  - praise：稱讚 AI（厲害、可愛、好棒）",
        "    ⚠ 若使用者稱讚的內容在對話歷史中不存在，不可歸類為 praise，應歸類為 questioning。",
        "  - flirt：撩 AI、試探感情",
        "  - farewell：告別、道晚安",
        "  - normal：一般閒聊",
        "",
        "【欄位判斷】",
        "  - requires_action：使用者是否真的要求 AI 完成任務或回答問題。",
        "  - target：使用者主要是在對誰說話。稱讚/質疑 AI 時為 assistant。",
        "",
        "⚠ 再次強調：你只能輸出一個 JSON 物件。不要有任何其他內容。"
    ]

    user_lines = [
        f"上一段對話：\n{history_context}" if history_context else "（尚無對話歷史）",
        f"使用者現在說：{state.get('user_input', '')}",
        f"Keyword evidence：{keyword_signals}",
        f"Keyword confidence：{keyword_confidence}",
        f"當前情緒值：{emotion:.3f}（-1=冷靜, 1=激動）",
        f"人格特質：{traits_text}",
        f"上一個任務狀態：{task_status or '無'}",
    ]

    system_prompt = "\n".join(system_lines)
    user_prompt = "\n\n".join(user_lines)
    return system_prompt, user_prompt
