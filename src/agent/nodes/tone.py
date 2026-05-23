from __future__ import annotations

import random
from agent.config import AgentConfig
from agent.state import AgentState
from agent.task_status import format_task_status_for_prompt

def build_tone_strategy(state: AgentState, config: AgentConfig) -> AgentState:
    stance = state.get("action_stance", "tsundere_service")
    emotion = state.get("emotion", 0.0)
    category = state.get("category", "normal")
    ambiguous = state.get("ambiguous_flag", False)
    sarcasm_possible = state.get("sarcasm_possible", False)
    
    # 決定字數
    response_length = "medium"
    if stance in ("dismissive", "deadpan"):
        response_length = "short"
    elif stance in ("chaotic_rant", "authoritative_bluffing", "emotion_burst"):
        response_length = "long"
    elif category == "sensitive_topic":
        response_length = "short"
        
    # 決定額外的語氣微調
    hints = "保持自然的實況主語氣。"
    
    if state.get("fake_praise"):
        task_status = format_task_status_for_prompt(state.get("last_task_status", {}))
        status_line = f"上一個相關任務狀態：{task_status}\n" if task_status else ""
        hints = (
            "【虛假稱讚修正 - 強制否認】\n"
            "使用者正在稱讚一個你根本沒做的事。對話事實優先於角色反應。\n"
            f"{status_line}"
            "你必須：1) 先直接說你沒做這件事；2) 反問對方是不是記錯或搞錯對象。"
        )
    elif sarcasm_possible:
        hints = (
            "【反諷/挖苦可能】\n"
            "先不要把表面稱讚當真。回應時要抓住對方可能在質疑或挖苦的語氣，"
            "可以冷淡反問或短促吐槽，但仍要回到實際問題。"
        )
    elif ambiguous:
        hints = (
            "【混合語境】\n"
            "使用者這句可能同時包含多個意圖。先回應最主要的語境，"
            "不要被單一觸發詞帶走，也不要過度腦補。"
        )
    elif stance == "tsundere_service":
        if emotion > 0.5:
            hints = "傲嬌成分加重，語氣可以再急躁一點。"
        elif emotion < -0.3:
            hints = "傲嬌成分減輕，帶一點不耐煩的冷淡。"
            
    return {
        "tone_hints": hints,
        "response_length": response_length,
        "flow_reason": f"category={category}, emotion={emotion:.2f}",
    }
