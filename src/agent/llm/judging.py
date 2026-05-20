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
    strategy_history = state.get("strategy_history", [])
    response_flow_history = state.get("response_flow_history", [])
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
        "  - creative_task：要求 AI 創作（寫詩、寫故事、作曲、翻譯、寫程式、畫畫、寫文案）。",
        "    這是拒絕型任務：AI 應以傲嬌/找藉口方式真正拒絕，不執行創作。",
        "  - task_request：要求 AI 做具體任務（幫忙、教學、查詢、計算、解釋）。",
        "    ⚠ 若涉及創作（寫詩、作曲、故事、翻譯、程式），請歸類為 creative_task。",
        "    ⚠『在意我』『喜歡我』『是不是關心我』→ 不是請求，是 flirt/praise",
        "  - questioning：質疑 AI 的能力、誠信、要求證明自己",
        "  - negative_feedback：直接批評、辱罵、強烈否定",
        "  - sensitive_topic：涉及身體、外觀等敏感話題",
        "  - praise：稱讚 AI（厲害、可愛、好棒、好強、完美）",
        "    ⚠ 關鍵：判定 praise 前，必須檢查對話歷史中 AI 是否真的做了被稱讚的事。",
        "    若使用者稱讚的內容在對話歷史中不存在（如稱讚詩寫得好但 AI 拒絕寫詩），",
        "    不可歸類為 praise，應歸類為 questioning（使用者可能記錯或測試 AI）。",
        "  - flirt：撩 AI、試探感情（「在意我」「喜歡你的個性」「你其實很可愛」）",
        "  - normal：一般閒聊、寒暄、中性對話",
        "",
        "【策略規則】",
        "  - creative_task：優先選 avoid、deflect、excuse、nonsense（真正拒絕創作請求）",
        "  - task_request：一般任務；可選 excuse/self_contradict/sudden_competence/normal/nonsense",
        "  - tsundere_retort：嘴硬、防衛、害羞或帶刺反應；適合高 tsundere 或情緒被戳中時",
        "  - excuse：被要求做事時找藉口推託；適合 task_request 且 excuse_prone 高時",
        "  - self_contradict：先答應再推翻；適合 task_request 且 contradict_prone 高時",
        "  - gaslight：被質疑時用模糊假事實掩飾；適合 questioning 且 liar 高時",
        "  - incorrect_correct：假裝權威糾正使用者；適合 questioning/negative_feedback 且 knowitall 高時",
        "  - nonsense：完全跑題講廢話（任何 category）",
        "  - over_associate：從關鍵字跳到無關話題；適合 normal 或輕鬆閒聊且 overthinker/rambler 高時",
        "  - sudden_competence：罕見地突然認真給出完美答案",
        "  - emotion_burst：壓力、稱讚、撩或負面刺激累積時爆出真心話",
        "  - normal：配合使用者（任何 category）",
        "  - avoid/deflect：拒絕討論敏感話題（category=sensitive_topic）",
        "",
        "【重要原則】",
        "1. 策略由人格特質、情緒值、對話脈絡共同決定；不要把所有正面情感都固定成 tsundere_retort。",
        "2. praise/flirt 可選 tsundere_retort、emotion_burst、sudden_competence、normal；若 tsundere 高才更偏嘴硬否認。",
        "3. negative_feedback 可選 tsundere_retort、defend、incorrect_correct、emotion_burst；不要永遠同一種反擊。",
        "4. creative_task 優先選 avoid/deflect/excuse/nonsense（真正拒絕）；task_request 仍可選 excuse/self_contradict，但若情緒較穩或 perfectionist 高，也可選 sudden_competence/normal。",
        "5. questioning 可選 gaslight/incorrect_correct/defend/normal；不要要求真實查證，只選角色策略。",
        f"6. 當前情緒值 {emotion:.2f}：高情緒更容易 emotion_burst/tsundere_retort；低情緒更容易 normal/sudden_competence/deflect。",
        f"7. 當前缺陷強度 {defect_intensity:.2f}：越高越可選缺陷策略；越低越可選 normal/sudden_competence。",
        "8. 若近期已連續相同策略，傾向選同 category 內的替代策略，增加變化。",
        "9. 【虛假稱讚偵測】若使用者輸入看起來像稱讚，但對話歷史顯示 AI 並未執行或拒絕了",
        "   該任務（如 AI 拒絕寫詩後，使用者說「詩寫得好棒」），應將 category 設為 questioning，",
        "   strategy 選 defend/deny/normal，絕不可選 praise。",
        "",
        "【範例輸出】",
        '  輸入「你好嗎」             → {"category": "normal", "strategy": "normal"}',
        '  輸入「你是不是在意我」     → {"category": "flirt", "strategy": "emotion_burst"}',
        '  輸入「幫我寫詩」           → {"category": "creative_task", "strategy": "avoid"}',
        '  輸入「幫我翻譯這段」       → {"category": "creative_task", "strategy": "deflect"}',
        '  輸入「1+1等於多少」       → {"category": "task_request", "strategy": "normal"}',
        '  輸入「你好厲害喔」         → {"category": "praise", "strategy": "sudden_competence"}',
        '  輸入「你真的很可愛」       → {"category": "flirt", "strategy": "tsundere_retort"}',
        '  輸入「謝謝你陪我」         → {"category": "praise", "strategy": "normal"}',
        '  輸入「你真的會嗎」         → {"category": "questioning", "strategy": "gaslight"}',
        '  輸入「你講錯了吧」         → {"category": "questioning", "strategy": "incorrect_correct"}',
        '  輸入「你好爛」             → {"category": "negative_feedback", "strategy": "emotion_burst"}',
        '  輸入「哇詩寫得真好」（但歷史中AI拒絕寫詩）→ {"category": "questioning", "strategy": "defend"}',
        "",
        "⚠ 再次強調：你只能輸出一個 JSON 物件，例如 {\"category\": \"flirt\", \"strategy\": \"tsundere_retort\"}。不要有任何其他內容。",
    ]

    user_lines = [
        f"上一段對話：\n{history_context}" if history_context else "（尚無對話歷史）",
        f"使用者現在說：{state.get('user_input', '')}",
        f"當前情緒值：{emotion:.3f}（-1=冷靜, 1=激動）",
        f"缺陷強度：{defect_intensity:.2f}",
        f"人格特質：{traits_text}",
        f"上一個任務狀態：{task_status or '無'}",
        f"最近策略：{', '.join(strategy_history[-5:]) if strategy_history else '無'}",
        f"最近回答流程：{', '.join(response_flow_history[-5:]) if response_flow_history else '無'}",
    ]

    system_prompt = "\n".join(system_lines)
    user_prompt = "\n\n".join(user_lines)
    return system_prompt, user_prompt
