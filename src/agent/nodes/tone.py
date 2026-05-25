from __future__ import annotations

import random
from agent.config import AgentConfig
from agent.state import AgentState, ResponseFlow
from agent.llm.vocab import get_emotion_zone
from agent.task_status import format_task_status_for_prompt


FLOW_LABELS: dict[str, str] = {
    "direct_answer": "直接回答",
    "dry_answer": "冷淡回答",
    "tease_then_answer": "吐槽後回答",
    "dodge_first": "先躲再答",
    "sudden_helpful": "突然可靠",
    "overhelp_then_deny": "幫太多再否認",
    "deny_then_soften": "否認後放軟",
    "emotional_leak": "真心漏出",
    "topic_bounce": "短暫跑題再拉回",
    "authority_bluff": "權威式硬凹",
    "deadpan_deny": "冷面否認",
    "counter_accuse": "倒打一耙",
    "spiral_rant": "暴走聯想",
    "slip_then_cover": "說漏嘴再掩飾",
    "burst_then_comply": "爆炸後照做",
    "hard_deflect": "堅定轉開",
}


FLOW_MATRIX: dict[str, dict[str, list[tuple[ResponseFlow, float]]]] = {
    "tsundere_service": {
        "cold": [("dry_answer", 0.35), ("tease_then_answer", 0.25), ("dodge_first", 0.20), ("direct_answer", 0.20)],
        "normal": [("tease_then_answer", 0.28), ("direct_answer", 0.24), ("deny_then_soften", 0.20), ("overhelp_then_deny", 0.16), ("dodge_first", 0.12)],
        "warm": [("emotional_leak", 0.28), ("deny_then_soften", 0.24), ("overhelp_then_deny", 0.22), ("tease_then_answer", 0.16), ("direct_answer", 0.10)],
        "hot": [("burst_then_comply", 0.30), ("deny_then_soften", 0.25), ("counter_accuse", 0.18), ("emotional_leak", 0.17), ("tease_then_answer", 0.10)],
    },
    "defensive_counter": {
        "cold": [("deadpan_deny", 0.35), ("counter_accuse", 0.30), ("dry_answer", 0.20), ("direct_answer", 0.15)],
        "normal": [("counter_accuse", 0.34), ("authority_bluff", 0.24), ("deny_then_soften", 0.22), ("tease_then_answer", 0.20)],
        "warm": [("counter_accuse", 0.30), ("slip_then_cover", 0.25), ("deny_then_soften", 0.25), ("emotional_leak", 0.20)],
        "hot": [("counter_accuse", 0.40), ("burst_then_comply", 0.30), ("authority_bluff", 0.18), ("slip_then_cover", 0.12)],
    },
    "dismissive": {
        "cold": [("hard_deflect", 0.42), ("dry_answer", 0.34), ("deadpan_deny", 0.24)],
        "normal": [("dry_answer", 0.34), ("hard_deflect", 0.30), ("topic_bounce", 0.20), ("dodge_first", 0.16)],
        "warm": [("topic_bounce", 0.30), ("deny_then_soften", 0.24), ("dry_answer", 0.24), ("hard_deflect", 0.22)],
        "hot": [("hard_deflect", 0.34), ("counter_accuse", 0.28), ("burst_then_comply", 0.20), ("dry_answer", 0.18)],
    },
    "chaotic_rant": {
        "cold": [("topic_bounce", 0.40), ("dry_answer", 0.25), ("spiral_rant", 0.20), ("direct_answer", 0.15)],
        "normal": [("topic_bounce", 0.38), ("spiral_rant", 0.32), ("tease_then_answer", 0.18), ("direct_answer", 0.12)],
        "warm": [("spiral_rant", 0.38), ("topic_bounce", 0.28), ("emotional_leak", 0.18), ("tease_then_answer", 0.16)],
        "hot": [("spiral_rant", 0.44), ("burst_then_comply", 0.24), ("topic_bounce", 0.20), ("counter_accuse", 0.12)],
    },
    "authoritative_bluffing": {
        "cold": [("authority_bluff", 0.42), ("deadpan_deny", 0.28), ("dry_answer", 0.18), ("direct_answer", 0.12)],
        "normal": [("authority_bluff", 0.44), ("tease_then_answer", 0.20), ("counter_accuse", 0.18), ("direct_answer", 0.18)],
        "warm": [("authority_bluff", 0.32), ("slip_then_cover", 0.26), ("tease_then_answer", 0.22), ("emotional_leak", 0.20)],
        "hot": [("counter_accuse", 0.34), ("authority_bluff", 0.30), ("burst_then_comply", 0.22), ("slip_then_cover", 0.14)],
    },
    "vulnerable_leak": {
        "cold": [("dry_answer", 0.30), ("emotional_leak", 0.28), ("deny_then_soften", 0.24), ("direct_answer", 0.18)],
        "normal": [("emotional_leak", 0.36), ("deny_then_soften", 0.28), ("slip_then_cover", 0.20), ("tease_then_answer", 0.16)],
        "warm": [("emotional_leak", 0.40), ("slip_then_cover", 0.24), ("deny_then_soften", 0.24), ("overhelp_then_deny", 0.12)],
        "hot": [("slip_then_cover", 0.34), ("emotional_leak", 0.30), ("burst_then_comply", 0.22), ("deny_then_soften", 0.14)],
    },
    "sudden_competence": {
        "cold": [("direct_answer", 0.40), ("sudden_helpful", 0.34), ("dry_answer", 0.16), ("overhelp_then_deny", 0.10)],
        "normal": [("sudden_helpful", 0.42), ("direct_answer", 0.28), ("overhelp_then_deny", 0.22), ("tease_then_answer", 0.08)],
        "warm": [("overhelp_then_deny", 0.36), ("sudden_helpful", 0.34), ("direct_answer", 0.16), ("emotional_leak", 0.14)],
        "hot": [("burst_then_comply", 0.30), ("overhelp_then_deny", 0.28), ("sudden_helpful", 0.24), ("emotional_leak", 0.18)],
    },
    "emotion_burst": {
        "cold": [("emotional_leak", 0.34), ("dry_answer", 0.24), ("slip_then_cover", 0.22), ("direct_answer", 0.20)],
        "normal": [("emotional_leak", 0.34), ("burst_then_comply", 0.28), ("slip_then_cover", 0.22), ("deny_then_soften", 0.16)],
        "warm": [("burst_then_comply", 0.36), ("emotional_leak", 0.30), ("slip_then_cover", 0.22), ("overhelp_then_deny", 0.12)],
        "hot": [("burst_then_comply", 0.44), ("emotional_leak", 0.26), ("counter_accuse", 0.16), ("slip_then_cover", 0.14)],
    },
    "deadpan": {
        "cold": [("deadpan_deny", 0.36), ("dry_answer", 0.34), ("direct_answer", 0.20), ("hard_deflect", 0.10)],
        "normal": [("dry_answer", 0.34), ("deadpan_deny", 0.26), ("direct_answer", 0.24), ("tease_then_answer", 0.16)],
        "warm": [("dry_answer", 0.30), ("deny_then_soften", 0.24), ("direct_answer", 0.22), ("emotional_leak", 0.14), ("deadpan_deny", 0.10)],
        "hot": [("deadpan_deny", 0.30), ("counter_accuse", 0.26), ("dry_answer", 0.24), ("burst_then_comply", 0.20)],
    },
}


def _weighted_pick(options: list[tuple[ResponseFlow, float]]) -> ResponseFlow:
    total = sum(max(0.0, weight) for _, weight in options)
    if total <= 0:
        return options[0][0]

    roll = random.random() * total
    cursor = 0.0
    for flow, weight in options:
        cursor += max(0.0, weight)
        if roll <= cursor:
            return flow
    return options[-1][0]


def _recent_repeat_count(items: list[str]) -> int:
    if not items:
        return 0
    last = items[-1]
    count = 0
    for item in reversed(items):
        if item == last:
            count += 1
        else:
            break
    return count


def _merge_flow_options(options: list[tuple[ResponseFlow, float]]) -> list[tuple[ResponseFlow, float]]:
    merged: dict[ResponseFlow, float] = {}
    for flow, weight in options:
        merged[flow] = merged.get(flow, 0.0) + max(0.0, weight)
    return [(flow, weight) for flow, weight in merged.items()]


def _apply_category_flow_adjustments(
    options: list[tuple[ResponseFlow, float]],
    category: str,
) -> list[tuple[ResponseFlow, float]]:
    adjusted: list[tuple[ResponseFlow, float]] = []
    for flow, weight in options:
        if category == "creative_task":
            if flow in ("hard_deflect", "dry_answer", "deadpan_deny"):
                weight *= 1.40
            elif flow in ("direct_answer", "sudden_helpful", "overhelp_then_deny", "burst_then_comply"):
                weight *= 0.45
        elif category == "task_request":
            if flow in ("direct_answer", "sudden_helpful", "overhelp_then_deny", "tease_then_answer", "burst_then_comply"):
                weight *= 1.22
            elif flow in ("hard_deflect", "deadpan_deny"):
                weight *= 0.70
        elif category in ("praise", "flirt"):
            if flow in ("emotional_leak", "deny_then_soften", "slip_then_cover", "tease_then_answer"):
                weight *= 1.25
            elif flow in ("hard_deflect", "authority_bluff", "deadpan_deny"):
                weight *= 0.75
        elif category in ("questioning", "negative_feedback"):
            if flow in ("counter_accuse", "authority_bluff", "deadpan_deny", "deny_then_soften"):
                weight *= 1.18
        elif category == "farewell":
            if flow in ("deny_then_soften", "emotional_leak", "tease_then_answer", "dry_answer"):
                weight *= 1.25
        adjusted.append((flow, weight))

    if category == "creative_task":
        adjusted.extend([("hard_deflect", 0.30), ("dry_answer", 0.12)])
    elif category == "task_request":
        adjusted.extend([("direct_answer", 0.10), ("sudden_helpful", 0.10)])
    elif category in ("praise", "flirt"):
        adjusted.extend([("emotional_leak", 0.10), ("deny_then_soften", 0.10)])
    elif category in ("questioning", "negative_feedback"):
        adjusted.extend([("counter_accuse", 0.08), ("authority_bluff", 0.08)])

    return _merge_flow_options(adjusted)


def _avoid_repeated_flow(
    options: list[tuple[ResponseFlow, float]],
    flow_history: list[str],
) -> list[tuple[ResponseFlow, float]]:
    if not flow_history:
        return options

    last = flow_history[-1]
    repeat_count = _recent_repeat_count(flow_history)
    if repeat_count >= 2:
        alternatives = [(flow, weight) for flow, weight in options if flow != last]
        if alternatives:
            return alternatives

    penalty = 0.45 if repeat_count == 1 else 0.15
    return [
        (flow, weight * penalty if flow == last else weight)
        for flow, weight in options
    ]


def _decide_response_flow(state: AgentState) -> tuple[ResponseFlow, str]:
    stance = state.get("action_stance", "tsundere_service")
    category = state.get("category", "normal")
    emotion = state.get("emotion", 0.0)
    emotion_zone = get_emotion_zone(emotion)
    matrix = FLOW_MATRIX.get(stance, FLOW_MATRIX["tsundere_service"])
    options = list(matrix.get(emotion_zone) or matrix["normal"])

    if state.get("fake_praise"):
        options = [("deadpan_deny", 0.55), ("counter_accuse", 0.35), ("deny_then_soften", 0.10)]
    else:
        options = _apply_category_flow_adjustments(options, category)

    flow_history = list(state.get("response_flow_history", []))
    options = _avoid_repeated_flow(options, flow_history)
    flow = _weighted_pick(options)
    label = FLOW_LABELS.get(flow, flow)
    return (
        flow,
        f"stance={stance}; category={category}; emotion_zone={emotion_zone}; response_flow={flow}({label})",
    )

def score_tsundere(state_vec: dict) -> float:
    return (
        state_vec.get("mood", 0.5) * 0.20 +
        state_vec.get("embarrassment", 0.0) * 0.30 +
        state_vec.get("masking", 0.0) * 0.30 +
        state_vec.get("playfulness", 0.0) * 0.15 -
        state_vec.get("hostility", 0.0) * 0.40
    )

def score_mock_angry(state_vec: dict) -> float:
    return (
        state_vec.get("annoyance", 0.0) * 0.35 +
        state_vec.get("playfulness", 0.0) * 0.40 +
        state_vec.get("dominance", 0.0) * 0.20 -
        state_vec.get("hostility", 0.0) * 0.50
    )

def score_firm_boundary(state_vec: dict) -> float:
    return (
        state_vec.get("boundary_pressure", 0.0) * 0.45 +
        state_vec.get("annoyance", 0.0) * 0.25 +
        state_vec.get("dominance", 0.0) * 0.25 -
        state_vec.get("playfulness", 0.0) * 0.30
    )

def score_soft_sad(state_vec: dict) -> float:
    return (
        state_vec.get("sadness", 0.0) * 0.45 +
        (1.0 - state_vec.get("energy", 0.5)) * 0.25 +
        state_vec.get("intimacy", 0.0) * 0.15 -
        state_vec.get("playfulness", 0.0) * 0.20
    )

def resolve_vtuber_emotion(state_vec: dict) -> dict:
    scores = {
        "firm_boundary": score_firm_boundary(state_vec),
        "soft_sad": score_soft_sad(state_vec),
        "mock_angry": score_mock_angry(state_vec),
        "tsundere": score_tsundere(state_vec),
    }
    
    # Priority check based on spec thresholds
    if scores["firm_boundary"] > 0.40:
        return {"base": "serious", "variant": "firm", "style": "boundary", "intensity": scores["firm_boundary"]}
    if scores["soft_sad"] > 0.40:
        return {"base": "sad", "variant": "soft", "style": "honest", "intensity": scores["soft_sad"]}
    if scores["mock_angry"] > 0.35:
        return {"base": "angry", "variant": "mock", "style": "teasing", "intensity": scores["mock_angry"]}
    if scores["tsundere"] > 0.45:
        return {"base": "shy", "variant": "happy", "style": "tsundere", "intensity": scores["tsundere"]}
        
    if state_vec.get("mood", 0.5) > 0.65 and state_vec.get("playfulness", 0.0) > 0.5:
        return {"base": "happy", "variant": "playful", "style": "teasing", "intensity": state_vec.get("mood", 0.5)}
        
    return {"base": "neutral", "variant": "calm", "style": "normal", "intensity": 0.5}

def build_acting_brief(resolved_emotion: dict) -> dict:
    style = resolved_emotion.get("style", "normal")
    if style == "boundary":
        return {
            "inner": "感到不適或被冒犯，需要維持界線",
            "outer": "嚴肅、直接、不留情面",
            "tone": "冷靜、堅定",
            "strategy": "直接拒絕或糾正，不帶玩笑語氣",
            "allowed_patterns": ["直接拒絕", "冷淡反問", "警告"],
            "avoid": ["笑", "開玩笑", "轉移話題", "接受"]
        }
    elif style == "teasing":
        return {
            "inner": "覺得有趣，想捉弄對方",
            "outer": "假裝生氣或挑釁，帶點壞心眼",
            "tone": "輕快、戲謔",
            "strategy": "反擊、吐槽、抓語病",
            "allowed_patterns": ["誇張反問", "假裝生氣", "反嘲諷"],
            "avoid": ["認真解釋", "冷漠句點", "直接道謝"]
        }
    elif style == "tsundere":
        return {
            "inner": "心裡高興但覺得害羞，不想承認",
            "outer": "嘴硬、假裝不在乎或嫌棄",
            "tone": "微慌、急躁、掩飾",
            "strategy": "先否認或吐槽，再間接接受或轉移話題",
            "allowed_patterns": ["假裝懷疑", "嘴硬否認", "反問", "結巴"],
            "avoid": ["直接說開心", "正式道謝", "長篇大論"]
        }
    elif style == "honest":
        return {
            "inner": "感到脆弱或感動",
            "outer": "坦率表達真實感受",
            "tone": "柔和、較慢、輕聲",
            "strategy": "誠實地說出心裡話，拉近距離",
            "allowed_patterns": ["直接道謝", "承認軟弱", "感性對話"],
            "avoid": ["嘴硬", "開玩笑", "過度誇張"]
        }
    else:
        return {
            "inner": "平靜",
            "outer": "自然放鬆",
            "tone": "實況主日常語氣",
            "strategy": "順著話題自然回應",
            "allowed_patterns": ["分享想法", "順勢接話"],
            "avoid": ["過度激動", "不自然的轉折"]
        }

def build_tone_strategy(state: AgentState, config: AgentConfig) -> AgentState:
    stance = state.get("action_stance", "tsundere_service")
    emotion = state.get("emotion", 0.0)
    category = state.get("category", "normal")
    ambiguous = state.get("ambiguous_flag", False)
    sarcasm_possible = state.get("sarcasm_possible", False)
    response_flow, flow_reason = _decide_response_flow(state)
    
    # VTuber Emotion Resolution
    character_state = state.get("character_state", {})
    resolved_emotion = resolve_vtuber_emotion(character_state)
    acting_brief = build_acting_brief(resolved_emotion)
    
    # 決定字數
    response_length = "medium"
    if stance in ("dismissive", "deadpan") or resolved_emotion.get("style") == "boundary":
        response_length = "short"
    elif stance in ("chaotic_rant", "authoritative_bluffing", "emotion_burst"):
        response_length = "long"
    elif category == "sensitive_topic":
        response_length = "short"

    if response_flow in ("dry_answer", "deadpan_deny", "hard_deflect"):
        response_length = "short"
    elif response_flow in ("spiral_rant", "burst_then_comply", "overhelp_then_deny"):
        response_length = "long"
        
    # 決定額外的語氣微調 (Legacy Fallback Hints)
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
        "response_flow": response_flow,
        "flow_reason": f"category={category}, emotion={emotion:.2f}; {flow_reason}",
        "resolved_emotion": resolved_emotion,
        "acting_brief": acting_brief
    }
