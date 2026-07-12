from __future__ import annotations


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


def build_expression_projection(acting_brief: dict, resolved_emotion: dict) -> dict:
    """Compile the performance brief into the small language-facing contract.

    ``acting_brief`` is also consumed by performance integrations, so it may
    contain inner-state and strategy details that must not become a second
    response router.  Keep only expression cues here; response goal/flow still
    owns what the reply must do and in which order.
    """
    intensity = resolved_emotion.get("intensity", 0.5)
    if isinstance(intensity, bool) or not isinstance(intensity, (int, float)):
        intensity = 0.5
    display = acting_brief.get("outer", "自然放鬆")
    tone = acting_brief.get("tone", "自然")
    avoid = acting_brief.get("avoid", [])
    if not isinstance(avoid, list):
        avoid = []
    return {
        "style": str(resolved_emotion.get("style", "normal")),
        "display": str(display),
        "tone": str(tone),
        "intensity": max(0.0, min(1.0, float(intensity))),
        "avoid": [str(item) for item in avoid[:2]],
    }
