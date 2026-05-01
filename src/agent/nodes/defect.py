from __future__ import annotations

import random

from agent.config import AgentConfig
from agent.state import AgentState, Strategy


def decide_defect_strategy(state: AgentState, config: AgentConfig) -> AgentState:
    category = state.get("category", "normal")
    emotion = state.get("emotion", 0.0)
    traits = state.get("traits", config.traits)
    uncertain = state.get("uncertain_flag", False)

    tsundere = traits.get("tsundere", 0.0)
    yandere = traits.get("yandere", 0.0)
    excuse_prone = traits.get("excuse_prone", 0.0)
    liar = traits.get("liar", 0.0)
    rambler = traits.get("rambler", 0.0)

    strategy: Strategy = "normal"
    defect_mode = "none"

    # ── 敏感話題：傲嬌迴避 ──
    if category == "sensitive_topic":
        strategy = "avoid" if emotion >= 0.2 else "deflect"
        defect_mode = "avoidance"

    # ── 負面回饋：否認 / 傲嬌反擊 / 防禦 ──
    elif category == "negative_feedback":
        if emotion >= 0.6:
            strategy = "deny"
            defect_mode = "angry_denial"
        elif tsundere >= 0.6:
            strategy = "tsundere_retort"
            defect_mode = "tsundere"
        else:
            strategy = "defend"
            defect_mode = "defend"

    # ── 任務請求：找藉口推托！──
    elif category == "task_request":
        # excuse_prone 越高、找藉口的機率越高
        if excuse_prone >= 0.5 and random.random() < excuse_prone:
            strategy = "excuse"
            defect_mode = "excuse"
        else:
            strategy = "normal"
            defect_mode = "cooperative_for_once"

    # ── 質問：一本正經說謊 ──
    elif category == "questioning":
        if liar >= 0.5 and random.random() < liar:
            strategy = "gaslight"
            defect_mode = "gaslight"
        else:
            strategy = "defend"
            defect_mode = "honest_defense"

    # ── 普通對話：有機率跑題說廢話 ──
    else:
        if uncertain and rambler >= 0.5:
            strategy = "nonsense"
            defect_mode = "rambling"
        elif emotion >= 0.7 and yandere >= 0.6:
            strategy = "defend"
            defect_mode = "yandere_protect"
        elif rambler >= 0.7 and random.random() < (rambler - 0.5):
            # 即使是正常對話，廢話王也可能突然跑題
            strategy = "nonsense"
            defect_mode = "random_ramble"

    return {"strategy": strategy, "defect_mode": defect_mode}
