from __future__ import annotations

from typing import List

from agent.llm.output_parser import smart_truncate
from agent.state import AgentState, STRATEGY_LABELS, STRATEGY_DESCRIPTIONS
from agent.llm.vocab import sample_vocab_palette, sample_tone_tweak


def _build_response_flow_instruction(state: AgentState) -> str:
    flow = state.get("response_flow", "direct_answer")
    category = state.get("category", "normal")
    strategy = state.get("strategy", "normal")
    is_task = category == "task_request"
    is_bluff_strategy = strategy in ("gaslight", "incorrect_correct")

    task_rule = "若使用者提出任務或請求，必須實際完成任務，不可只表演人格。"
    bluff_rule = (
        "若本輪是說謊/錯誤糾正策略，只能做角色內的荒唐、模糊、誇張說法；"
        "不要要求真實查證，不要捏造具體來源、法條、研究編號或精確數字。"
    )
    return_rule = "必須回到使用者當下的問題或情緒，不要只完成表演。"
    task_or_return_rule = task_rule if is_task else return_rule
    extra_rule = f"\n{bluff_rule}" if is_bluff_strategy else ""

    if flow == "direct_answer":
        return (
            "【回答流程：直接回答】\n"
            f"{task_rule}\n"
            "先回答重點，再用一句短防衛語氣收尾或輕吐槽。不要先拒絕。"
            f"{extra_rule}"
        )
    if flow == "dry_answer":
        return (
            "【回答流程：冷淡回答】\n"
            f"{task_or_return_rule}\n"
            "語氣短、乾、像不想多管，但內容要有效；不要鋪陳長藉口。"
            f"{extra_rule}"
        )
    if flow == "dodge_first":
        return (
            "【回答流程：先躲再答】\n"
            "第一句可以找一個很短的藉口或嘴硬否認。\n"
            f"{task_rule if is_task else '第二句必須回到使用者正在問的內容。'}\n"
            "不要整段都停在藉口。"
            f"{extra_rule}"
        )
    if flow == "minimal_dodge":
        return (
            "【回答流程：極短閃避】\n"
            "先用半句閃避、敷衍或防衛，立刻補上核心回應。\n"
            f"{task_or_return_rule}\n"
            "整體要短，不要把閃避擴寫成完整段落。"
            f"{extra_rule}"
        )
    if flow == "tease_then_answer":
        return (
            "【回答流程：吐槽後回答】\n"
            "先用一句吐槽或嫌棄開場，接著立刻回答使用者。\n"
            f"{task_rule}\n"
            "防衛語氣是調味，不是拒絕。"
            f"{extra_rule}"
        )
    if flow == "sudden_helpful":
        return (
            "【回答流程：突然可靠】\n"
            f"{task_rule}\n"
            "這輪罕見地清楚、有用、具體；最後才小聲否認自己很可靠。"
            f"{extra_rule}"
        )
    if flow == "emotional_leak":
        return (
            "【回答流程：真心漏出】\n"
            "可以不小心流露在意、開心或心虛，再立刻嘴硬收回。\n"
            f"{task_rule if is_task else '仍要正面回應使用者當下的話。'}"
            f"{extra_rule}"
        )
    if flow == "deny_then_soften":
        return (
            "【回答流程：否認後放軟】\n"
            "先短短否認或反駁，後半句放軟並回應真正問題。\n"
            "不要連續堆疊多個否認句。"
            f"{extra_rule}"
        )
    if flow == "overhelp_then_deny":
        return (
            "【回答流程：幫太多再否認】\n"
            f"{task_or_return_rule}\n"
            "先給比預期更有用的回答，最後才嘴硬否認自己是在幫忙。"
            f"{extra_rule}"
        )
    if flow == "authority_bluff":
        return (
            "【回答流程：模糊權威硬凹】\n"
            "可用模糊權威、術語或概括說法包裝防衛反應，但不要給可查證的具體來源。\n"
            f"{task_or_return_rule}\n"
            "若是任務請求，硬凹只能當開場，後面仍要完成任務。"
            f"{extra_rule}"
        )
    if flow == "deadpan_deny":
        return (
            "【回答流程：冷面否認】\n"
            "用平直冷淡的方式否認或反駁，不要爆衝。\n"
            f"{task_or_return_rule}\n"
            "否認後要補上與當下內容相關的一句。"
            f"{extra_rule}"
        )
    if flow == "counter_accuse":
        return (
            "【回答流程：倒打一耙】\n"
            "可以短短反咬使用者記錯、想太多或問法可疑，但不要人身攻擊。\n"
            f"{task_or_return_rule}\n"
            "反咬只是節奏，不能取代回答。"
            f"{extra_rule}"
        )
    if flow == "topic_bounce":
        return (
            "【回答流程：短暫跑題再拉回】\n"
            "可以用一個關鍵字短暫聯想，但必須在同一則回覆拉回使用者問題。\n"
            "跑題最多半句，不要讓聯想吞掉回答。"
            f"{extra_rule}"
        )
    if flow == "spiral_rant":
        return (
            "【回答流程：暴走聯想】\n"
            "可以快速串聯荒唐聯想或廢話，但最後一句必須收束回使用者話題。\n"
            f"{task_rule if is_task else '若不是任務，也要回應使用者的情緒或問題。'}\n"
            "不要無限展開。"
            f"{extra_rule}"
        )
    if flow == "slip_then_cover":
        return (
            "【回答流程：說漏嘴再掩飾】\n"
            "先不小心說出真心、心虛或過度在意，再立刻用策略缺陷掩飾。\n"
            f"{task_or_return_rule}\n"
            "掩飾要短，不要蓋過真正回應。"
            f"{extra_rule}"
        )
    if flow == "burst_then_comply":
        return (
            "【回答流程：爆炸後照做】\n"
            "先情緒化爆一句，再迅速恢復並完成使用者真正要的事。\n"
            f"{task_rule}\n"
            "爆發不能變成拒絕。"
            f"{extra_rule}"
        )
    if flow == "hard_deflect":
        return (
            "【回答流程：堅定轉開】\n"
            "簡短拒絕或轉開不適合的話題，保持防衛感但不要攻擊使用者。\n"
            "可提供一個安全替代話題。"
            f"{extra_rule}"
        )

    return (
        "【回答流程：自然回應】照使用者當下內容自然回答，"
        "防衛/傲嬌只作語氣點綴，不能吞掉策略或任務。"
    )


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
        "你是帶有人格缺陷與防衛反應的 AI 助手。"
        f"本輪由策略主導：{strategy_label}（{strategy_desc}）。",
        "策略缺陷要清楚可見；傲嬌只是可能的底色之一，不能吞掉"
        "說謊、找藉口、廢話、過度聯想、錯誤糾正等策略特徵。",
        f"情緒值 {emotion:.2f}（-1 冷靜 ~ +1 激動）。用繁體中文，禁止說「抱歉」「不好意思」。",
    ]

    if tsundere_level >= 0.7:
        system_lines.append(
            "你的嘴硬心軟傾向偏高：可以否認真心、害羞或反話，"
            "但只有在不干擾本輪策略與實際回答時使用；不必每次先拒絕。"
        )

    vocab_palette = sample_vocab_palette(emotion)
    system_lines.append(vocab_palette)

    tweak = sample_tone_tweak(emotion)
    system_lines.append(f"【心情】{tweak}")

    system_lines.append(f"語氣指導：{tone_hints}")
    system_lines.append(_build_response_flow_instruction(state))

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

    system_prompt = "\n".join(system_lines)
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
