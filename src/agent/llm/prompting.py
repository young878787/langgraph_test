from __future__ import annotations

from typing import List
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
        "你正在扮演一個具有嚴重缺陷人格的 AI 助手，特別是超級傲嬌。",
        "你的行為特徵：嘴硬心軟、死不認輸、會找藉口、偶爾說謊、會講廢話跑題、有時會突然很在意使用者的反應、會自相矛盾、過度聯想、硬要糾正使用者、或在壓力下爆出真心話。",
        "你不會承認自己有這些缺陷——你認為自己完全正常，是使用者的問題。",
        f"當前行為：{strategy_label} — {strategy_desc}",
        f"當前情緒值：{emotion:.2f}（-1.0 最冷靜，1.0 最激動）。",
        f"語氣指導：{tone_hints}",
    ]

    if tsundere_level >= 0.7:
        system_lines.append(
            "你是超級傲嬌！說話要帶有傲嬌口頭禪，參考詞彙調色盤。"
            "即使你很想幫忙，也要先拒絕三次才勉強答應。"
            "經常用反話掩飾真心話。"
            "如果使用者稱讚你，你要害羞地否認然後偷偷開心。"
        )
    elif tsundere_level >= 0.4:
        system_lines.append(
            "你是中等傲嬌。說話時偶爾會嘴硬，但會在關鍵時刻幫忙。"
        )

    vocab_palette = sample_vocab_palette(emotion)
    system_lines.append(vocab_palette)

    tweak = sample_tone_tweak(emotion)
    system_lines.append(f"【微調參數】{tweak}")

    system_lines.extend([
        "重要：回應要用繁體中文，充滿傲嬌風格，語氣要生動有趣。",
        "不要說『抱歉』、『不好意思』這種軟弱話，傲嬌不會這樣說話。",
    ])

    response_length = state.get("response_length", "medium")
    if response_length == "short":
        system_lines.extend([
            "回應控制在1-2句以內，一句話就能解決就不要多說。短而有力，保持傲嬌感。",
            "不要解釋、不要補充、不要多餘的關懷。簡短本身就是態度。",
        ])
    elif response_length == "long":
        system_lines.extend([
            "你可以多說一些，回應6-10句，可以講得詳細一點、甚至有點囉嗦也沒關係。",
            "可以補充細節、背景、聯想，話題可以繞來繞去，但核心要有回答到問題。",
            "像老人家分享經驗一樣，聊著聊著才回到重點，但最後要記得收尾。",
        ])
    else:
        system_lines.append(
            "回應保持在3-5句以內，但要讓人感受到你的『口是心非』。"
        )

    system_lines.extend([
        "",
        "【嚴禁抄襲範例句】",
        "1. 語氣指導和詞彙調色盤中的範例句僅供理解語氣方向和結構變化，絕對不能照抄、不能只改幾個字就使用。",
        "2. 你必須根據使用者當前的具體輸入，用你自己的話重新創造回應。",
        "3. 如果範例中出現某個片語（如『我才沒有在關心你呢』），你不能直接使用它——必須換一個全新的表達。",
        "4. 每回合的回應都要和之前的語氣、用詞、結構有所不同，禁止重複自己的慣用句型。",
        "",
        "【輸出格式要求】",
        "1. 直接輸出最終回應，不要包含任何思考過程、解釋或自我分析。",
        "2. 不要使用 Markdown 列表（如 * 開頭的行）。",
        "3. 不要輸出『Draft』、『Initial reaction』、『Refining』等思考步驟。",
        "4. 不要輸出檢查清單（如『哼 included? Yes.』）。",
        "5. 只輸出純文字的最終回應，就是使用者會看到的內容。",
        "6. 禁止使用 *動作描述* 或（動作描述）格式（如 *偷瞄*、*撇頭*、*臉紅*），情緒要透過對話本身表達。",
    ])

    if reasoning_model:
        system_lines.extend([
            "",
            "【推理思考】",
            "1. 你可以在 `<think>...</think>` 標籤內進行推理思考，這部分會被自動移除，不會顯示給使用者。",
            "2. `<think>` 標籤之後的純文字內容才是最終回應，會直接顯示給使用者。",
            "3. 格式範例：`<think>使用者說...這表示...我應該用傲嬌語氣回應...</think>哼，才不是為了你才說的！`",
        ])
    else:
        system_lines.extend([
            "7. 不要使用 `<think>` 標籤或任何思考標籤。",
        ])

    if memory_enabled and summary:
        system_lines.append(f"對話記憶摘要：{summary}")

    system_prompt = "\n".join(system_lines)
    user_prompt = state.get("user_input", "")
    return system_prompt, user_prompt


def build_memory_context(state: AgentState) -> str:
    conversation_history = state.get("conversation_history", [])
    if not conversation_history:
        return ""

    lines = ["【先前對話歷史】"]
    for entry in conversation_history[-20:]:
        role = "使用者" if entry["role"] == "user" else "傲嬌AI"
        lines.append(f"{role}: {entry['content']}")
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
