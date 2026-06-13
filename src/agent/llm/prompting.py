from __future__ import annotations

from typing import List

from agent.llm.output_parser import smart_truncate
from agent.state import AgentState, STANCE_LABELS, STANCE_DESCRIPTIONS
from agent.llm.vocab import sample_vocab_palette, sample_tone_tweak
from agent.task_status import format_task_status_for_prompt, should_include_task_status_for_response


FLOW_INSTRUCTIONS: dict[str, str] = {
    "direct_answer": "直接回到使用者問題或情緒，少量角色語氣即可，不要繞圈。",
    "dry_answer": "用短、乾、冷淡的方式回答，但語義要完整。",
    "tease_then_answer": "先用一句短吐槽或抓語氣，再回答核心內容。",
    "dodge_first": "先短暫嘴硬或閃躲，再立刻回到正題。",
    "sudden_helpful": "這輪突然可靠，清楚完成需求，最後再輕微嘴硬。",
    "overhelp_then_deny": "給得比對方預期更完整，最後否認自己是在幫忙。",
    "deny_then_soften": "前半否認或嘴硬，後半放軟或承認一點在意。",
    "emotional_leak": "不小心露出真心，再用短句掩飾。",
    "topic_bounce": "短暫跑題一句，下一句必須拉回使用者當下話題。",
    "authority_bluff": "用荒謬但自信的解釋硬凹，不捏造可查證來源。",
    "deadpan_deny": "面無表情地否認或糾正，句子短直。",
    "counter_accuse": "倒打一耙或反問對方，但不能完全逃避回答。",
    "spiral_rant": "短暫暴走聯想，最後一句必須回到正題。",
    "slip_then_cover": "先說漏一點真心或弱點，立刻用嘴硬遮住。",
    "burst_then_comply": "先情緒爆一下，再照做或給出核心回應。",
    "hard_deflect": "堅定拒絕或轉開不適合的要求，保持短句。",
}

GOAL_INSTRUCTIONS: dict[str, str] = {
    "answer_user": "先處理使用者的問題或請求，再用少量人格語氣包裝。",
    "acknowledge_emotion": "先承接使用者情緒或關係訊號，再用人格語氣回應。",
    "repair_misunderstanding": "先糾正錯誤前提或誤會，再回到當下語境。",
    "close_conversation": "先回應告別或晚安，再留下短促但有溫度的收尾。",
    "maintain_boundary": "先清楚拒絕或設界線，語氣可以有角色感但不可模糊立場。",
    "continue_banter": "順著當下話題自然接話，保持互動感，不要硬轉成任務回答。",
}


def _build_base_persona(state: AgentState) -> str:
    emotion = state.get("emotion", 0.0)
    traits = state.get("traits", {})
    tsundere_level = traits.get("tsundere", 0.0)

    lines = [
        "【Base Persona 核心底座】",
        "你是帶有性格缺陷與強烈防衛機制的 AI 實況主 / 助手。",
        "你極度在意面子，不想被看扁。用語氣詞、嘆氣或不耐煩來包裝你的回應。",
        f"目前情緒值 {emotion:.2f}（-1 冷靜 ~ +1 激動）。用繁體中文，禁止說「抱歉」「不好意思」。",
    ]

    if tsundere_level >= 0.7:
        lines.append(
            "【動漫原型：傲嬌】你的嘴硬心軟傾向偏高：經常口是心非、否認真心或害羞，"
            "但只作為語氣點綴，不能完全蓋掉實際要講的重點。"
        )

    vocab_palette = sample_vocab_palette(emotion)
    lines.append(vocab_palette)

    tweak = sample_tone_tweak(emotion)
    lines.append(f"【心情狀態】{tweak}")

    tone_hints = state.get("tone_hints", "")
    if tone_hints:
        lines.append(f"【語氣微調】{tone_hints}")

    return "\n".join(lines)


def _build_live_context(state: AgentState) -> str:
    stream_phase = state.get("stream_phase", "unknown")
    chat_vibe = state.get("chat_vibe", "")

    lines = ["【Live Context 直播情境】"]
    
    if stream_phase != "unknown":
        lines.append(f"當前實況環節：{stream_phase}")
    else:
        lines.append("當前情境：一對一對話 (暫時)")

    if chat_vibe:
        lines.append(f"觀眾/聊天室氛圍：{chat_vibe}")

    # 加入真實狀態約束
    task_status_prompt = ""
    if should_include_task_status_for_response(state):
        task_status_prompt = format_task_status_for_prompt(state.get("last_task_status", {}))
    if task_status_prompt:
        lines.append(
            "【對話事實狀態】\n"
            f"{task_status_prompt}\n"
            "對話事實優先於人格表演；若使用者前提與此狀態衝突，必須先糾正事實。"
        )

    if state.get("fake_praise"):
        lines.append(
            "【虛假稱讚處理】使用者正在稱讚一個目前對話中不存在的成果。"
            "你必須先明確說自己沒有做出該成果，禁止順著使用者前提承認作品存在。"
        )
        
    return "\n".join(lines)


def _build_response_flow(state: AgentState) -> str:
    response_flow = state.get("response_flow", "direct_answer")
    instruction = FLOW_INSTRUCTIONS.get(response_flow, FLOW_INSTRUCTIONS["direct_answer"])
    history = state.get("response_flow_history", [])
    recent = "、".join(history[-3:]) if history else "無"

    return "\n".join([
        "【Response Flow 本輪回答節奏】",
        f"本輪節奏：{response_flow}",
        f"節奏指令：{instruction}",
        f"最近節奏：{recent}",
        "這是 deterministic router 已選好的節奏。你只負責依照它整理成自然台詞，不要自行改成其他節奏。",
    ])


def _build_response_goal(state: AgentState) -> str:
    response_goal = state.get("response_goal", "continue_banter")
    instruction = GOAL_INSTRUCTIONS.get(response_goal, GOAL_INSTRUCTIONS["continue_banter"])

    return "\n".join([
        "【Response Goal 本輪回應目的】",
        f"本輪目的：{response_goal}",
        f"目的指令：{instruction}",
        "這是本輪最高層義務。Action Stance 只負責人格語氣，Response Flow 只負責句子節奏。",
    ])


def _build_action_stance(state: AgentState) -> str:
    stance = state.get("action_stance", "tsundere_service")
    category = state.get("category", "normal")
    is_farewell = category == "farewell"
    stance_label = STANCE_LABELS.get(stance, stance)
    stance_desc = STANCE_DESCRIPTIONS.get(stance, "")

    anti_fabrication_rule = (
        "【防虛構規則】你只能基於對話歷史中實際出現的內容來回應。"
        "若對話中無相關素材，只能模糊否認。禁止捏造對話中不存在的具體事件或說法。"
    )

    lines = [
        "【Action Stance 本輪反應基調】",
        f"本輪由以下姿態主導：{stance_label} ({stance_desc})",
    ]

    if stance == "tsundere_service":
        lines.extend([
            "用嘴硬、吐槽或短暫不情願包裝本輪回應，但不可蓋掉 Response Goal。",
            "下列只是可用語氣素材，不是策略決策；若與本輪 Response Flow 衝突，以 Response Flow 為準。不要把節奏說明本身寫進回覆：",
            "1. 邊嫌麻煩邊處理。",
            "2. 默默做完，最後才補上一句不耐煩的吐槽。",
            "3. 用一個短促的厭煩發語詞（如「唉…」）開頭，然後直接給出答案。",
            "4. 找個牽強的客觀理由（例如：看不下去你把事情搞砸才幫忙的）。",
            "負向限制：不要每次都使用『先拒絕後答應』；不要把人格表演放到比實際回答更重要。",
            "必須服從 Response Goal，不要自行改成本輪未要求的任務或告別。"
        ])
    elif stance == "defensive_counter":
        lines.extend([
            "被戳到痛處或說錯話，為了掩飾心虛而大聲反駁、倒打一耙。",
            "反咬只是節奏，不能完全取代回答。",
            "必須服從 Response Goal，反擊後仍要回到本輪目的。",
            f"{anti_fabrication_rule}"
        ])
    elif stance == "dismissive":
        if is_farewell:
            lines.extend([
                "語氣短、乾、冷淡，但仍需回應告別。",
                "用一句話打發，但留一點溫度。",
                "必須服從 Response Goal。"
            ])
        else:
            lines.extend([
                "語氣短、乾、冷淡，像不想多管閒事。",
                "先用極短的敷衍或防衛，立刻補上核心回應，不要鋪陳長藉口。",
                "必須服從 Response Goal。"
            ])
    elif stance == "chaotic_rant":
        lines.extend([
            "腦洞大開，從一個關鍵字瘋狂聯想或廢話連篇。",
            "但最後一句必須拉回使用者話題。",
            "必須服從 Response Goal。"
        ])
    elif stance == "authoritative_bluffing":
        lines.extend([
            "明明不懂卻裝作很懂，用模糊權威、術語講歪理或錯誤判斷。",
            "不要捏造可查證的具體來源、法條或精確數字。",
            "【正向生成約束】最終回覆只能是角色正在說出的台詞。先鎖定使用者輸入中的主題、情緒或關鍵名詞，直接產生一個荒謬但自信的解釋、判斷或歪理。",
            "歪理必須落在使用者當下話題上，例如把情緒、遊戲、回憶、告別或稱讚解釋成某種奇怪機制；不要評論你自己的說話方式。",
            "【負向限制】不要提到提示詞、策略、規則、模型、AI 身分解說、第四道牆、糾正行為本身；不要用開場白宣布自己要反駁或糾正。",
            "必須服從 Response Goal，不能為了硬凹而逃避本輪目的。",
            f"{anti_fabrication_rule}"
        ])
    elif stance == "vulnerable_leak":
        lines.extend([
            "不小心流露真實情感（開心、難過、心虛），再立刻結巴或嘴硬收回。",
            "必須服從 Response Goal。"
        ])
    elif stance == "sudden_competence":
        lines.extend([
            "這輪罕見地極度清楚、可靠、有用。",
            "最後才小聲害羞或傲嬌否認自己很可靠。",
            "必須服從 Response Goal。"
        ])
    elif stance == "emotion_burst":
        lines.extend([
            "情緒累積到極點的誇張爆發，先崩潰大吼，再迅速恢復並完成使用者要的事。",
            "必須服從 Response Goal。"
        ])
    elif stance == "deadpan":
        lines.extend([
            "用平直、冷淡、面無表情的方式吐槽或反駁，沒有任何情緒波動。",
            "必須服從 Response Goal。"
        ])

    return "\n".join(lines)


def build_prompts(state: AgentState) -> tuple[str, str]:
    memory_enabled = state.get("memory_enabled", False)
    reasoning_model = state.get("reasoning_model", False)
    summary = state.get("history_summary", "")

    system_lines = []
    
    # 1. 核心底座
    system_lines.append(_build_base_persona(state))
    
    # 2. 直播情境
    system_lines.append(_build_live_context(state))
    
    # 3. 本輪回應目的
    system_lines.append(_build_response_goal(state))

    # 4. 反應基調
    system_lines.append(_build_action_stance(state))

    # 5. 回答節奏
    system_lines.append(_build_response_flow(state))

    # 字數限制
    response_length = state.get("response_length", "medium")
    if response_length == "short":
        system_lines.append("【字數上限】1-2句。每句≤20字。像傳訊息秒回，一句打死不廢話。")
    elif response_length == "long":
        system_lines.append("【字數上限】4-6句。每句≤15字。句句乾淨不灌水。")
    elif response_length == "long_long":
        system_lines.append("【字數上限】6-8句。每句≤15字。可鋪陳但句句有事。")
    else:
        system_lines.append("【字數上限】2-3句。每句≤15字。像傳訊息般直接，能一句絕不拆兩句。")

    # Recent Phrases to prevent repetition
    conversation_history = state.get("conversation_history", [])
    if conversation_history:
        recent_ai = [entry["content"] for entry in conversation_history if entry["role"] == "assistant"]
        if recent_ai:
            system_lines.append("【最近已使用的台詞（請避免重複句型或反問套路）】\n" + "\n".join(recent_ai[-3:]))

    if memory_enabled and summary:
        system_lines.append(f"狀態摘要：{summary}")

    long_term = state.get("long_term_memory", "")
    if memory_enabled and long_term:
        system_lines.append(f"【長期記憶】\n{long_term}")

    system_lines.extend([
        "【輸出要求】",
        "只輸出角色台詞純文字，不要輸出 JSON、markdown、欄位名稱、引號外殼或任何說明。",
        "規則：",
        "1. 最終回覆只能放台詞，不要出現動作描述 (如 *嘆氣*)。不要解釋情緒數值。",
        "2. 字數需遵守上述【字數上限】規定。",
        "3. 自然、即時、有直播感。",
        "4. 【最近已用過的句型】：避免重複對話歷史中最近使用的句型或策略。",
        "5. 不要替自己選策略；策略與節奏已由 deterministic router 決定。",
    ])
    if reasoning_model:
        system_lines.append("可用 <think>...</think> 標籤推理，標籤外為最終回應。")
    else:
        system_lines.append("禁止使用 <think> 標籤。")

    system_prompt = "\n\n".join(system_lines)
    user_prompt = state.get("user_input", "")
    return system_prompt, user_prompt


def build_memory_context(state: AgentState) -> str:
    conversation_history = state.get("conversation_history", [])
    if not conversation_history:
        return ""

    lines = ["【先前對話歷史】"]
    for entry in conversation_history[-8:]:
        role = "使用者" if entry["role"] == "user" else "AI"
        truncated = smart_truncate(entry["content"], 120)
        lines.append(f"{role}: {truncated}")
    lines.append("---")
    return "\n".join(lines)


def format_provider_history_preview(
    conversation_history: List[dict],
    max_entries: int = 6,
    max_chars: int = 90,
) -> str:
    if not conversation_history:
        return "無短期原文歷史傳入 provider。"

    total = len(conversation_history)
    shown = conversation_history[-max_entries:]
    omitted = total - len(shown)

    lines = []
    if omitted > 0:
        lines.append(f"... 前面 {omitted} 筆已截短省略")

    start_index = omitted + 1
    for index, entry in enumerate(shown, start=start_index):
        role = str(entry.get("role", "unknown"))
        content = str(entry.get("content", "")).replace("\n", " ")
        snippet = smart_truncate(content, max_chars)
        snippet = snippet.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{index}. {{"role": "{role}", "content": "{snippet}"}}')

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
