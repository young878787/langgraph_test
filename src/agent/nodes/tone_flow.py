from __future__ import annotations

import random

from agent.llm.vocab import get_emotion_zone
from agent.state import AgentState, ResponseFlow


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


def _apply_goal_flow_adjustments(
    options: list[tuple[ResponseFlow, float]],
    response_goal: str,
) -> list[tuple[ResponseFlow, float]]:
    adjusted: list[tuple[ResponseFlow, float]] = []
    for flow, weight in options:
        if response_goal == "answer_user":
            if flow in ("direct_answer", "sudden_helpful", "overhelp_then_deny", "tease_then_answer", "burst_then_comply"):
                weight *= 1.25
            elif flow in ("hard_deflect", "deadpan_deny", "counter_accuse", "topic_bounce"):
                weight *= 0.55
            elif flow == "authority_bluff":
                weight *= 0.75
        elif response_goal == "maintain_boundary":
            if flow in ("hard_deflect", "dry_answer", "deadpan_deny"):
                weight *= 1.35
            elif flow in ("sudden_helpful", "overhelp_then_deny", "burst_then_comply", "emotional_leak", "topic_bounce"):
                weight *= 0.50
            elif flow == "direct_answer":
                weight *= 0.75
        elif response_goal == "close_conversation":
            if flow in ("deny_then_soften", "emotional_leak", "dry_answer", "tease_then_answer"):
                weight *= 1.30
            elif flow in ("spiral_rant", "authority_bluff", "counter_accuse", "hard_deflect", "topic_bounce"):
                weight *= 0.45
        elif response_goal == "acknowledge_emotion":
            if flow in ("emotional_leak", "deny_then_soften", "slip_then_cover", "tease_then_answer", "direct_answer"):
                weight *= 1.25
            elif flow in ("authority_bluff", "counter_accuse", "hard_deflect", "deadpan_deny"):
                weight *= 0.60
        elif response_goal == "repair_misunderstanding":
            if flow in ("deadpan_deny", "dry_answer", "deny_then_soften", "direct_answer", "counter_accuse"):
                weight *= 1.25
            elif flow in ("spiral_rant", "topic_bounce", "overhelp_then_deny", "emotional_leak"):
                weight *= 0.55
        adjusted.append((flow, weight))

    if response_goal == "answer_user":
        adjusted.extend([("direct_answer", 0.12), ("sudden_helpful", 0.08)])
    elif response_goal == "maintain_boundary":
        adjusted.extend([("hard_deflect", 0.14), ("dry_answer", 0.08)])
    elif response_goal == "close_conversation":
        adjusted.extend([("deny_then_soften", 0.10), ("dry_answer", 0.08)])
    elif response_goal == "acknowledge_emotion":
        adjusted.extend([("emotional_leak", 0.10), ("deny_then_soften", 0.08)])
    elif response_goal == "repair_misunderstanding":
        adjusted.extend([("deadpan_deny", 0.10), ("direct_answer", 0.08)])

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


def decide_response_flow(state: AgentState) -> tuple[ResponseFlow, str]:
    stance = state.get("action_stance", "tsundere_service")
    category = state.get("category", "normal")
    response_goal = state.get("response_goal", "continue_banter")
    emotion = state.get("emotion", 0.0)
    emotion_zone = get_emotion_zone(emotion)
    matrix = FLOW_MATRIX.get(stance, FLOW_MATRIX["tsundere_service"])
    options = list(matrix.get(emotion_zone) or matrix["normal"])

    if state.get("fake_praise"):
        options = [("deadpan_deny", 0.55), ("counter_accuse", 0.35), ("deny_then_soften", 0.10)]
    else:
        options = _apply_category_flow_adjustments(options, category)
        options = _apply_goal_flow_adjustments(options, response_goal)

    flow_history = list(state.get("response_flow_history", []))
    options = _avoid_repeated_flow(options, flow_history)
    flow = _weighted_pick(options)
    label = FLOW_LABELS.get(flow, flow)
    return (
        flow,
        f"stance={stance}; category={category}; goal={response_goal}; emotion_zone={emotion_zone}; response_flow={flow}({label})",
    )
