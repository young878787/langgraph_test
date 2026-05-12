from __future__ import annotations

from typing import Dict, List, Literal, TypedDict

from agent.config import AgentConfig

Category = Literal["normal", "negative_feedback", "sensitive_topic", "task_request", "questioning", "praise", "flirt"]
ResponseLength = Literal["short", "medium", "long", "long_long"]
ResponseFlow = Literal[
    "direct_answer",
    "dry_answer",
    "dodge_first",
    "minimal_dodge",
    "tease_then_answer",
    "sudden_helpful",
    "emotional_leak",
    "deny_then_soften",
    "topic_bounce",
    "overhelp_then_deny",
    "authority_bluff",
    "deadpan_deny",
    "counter_accuse",
    "spiral_rant",
    "slip_then_cover",
    "burst_then_comply",
    "hard_deflect",
]
Strategy = Literal[
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
]
JudgeSource = Literal["llm", "rule"]

STRATEGY_LABELS: dict[str, str] = {
    "normal": "平常",
    "avoid": "迴避",
    "deflect": "轉移話題",
    "defend": "防禦",
    "deny": "憤怒否認",
    "tsundere_retort": "傲嬌反擊",
    "excuse": "找藉口",
    "gaslight": "說謊",
    "nonsense": "廢話",
    "self_contradict": "自相矛盾",
    "over_associate": "過度聯想",
    "incorrect_correct": "錯誤糾正",
    "sudden_competence": "突然正常",
    "emotion_burst": "情緒噴泉",
}

STRATEGY_DESCRIPTIONS: dict[str, str] = {
    "normal": "平常的嘴硬心軟，否認完會偷偷幫忙",
    "avoid": "禮貌但堅定地拒絕談論，帶一點不自在",
    "deflect": "轉移話題，不正面回應",
    "defend": "為自己辯護，但語氣中透露在意",
    "deny": "強烈否認，情緒化反擊",
    "tsundere_retort": "嘴硬心軟，用帶刺的話掩飾真心話",
    "excuse": "找各種荒唐藉口推託",
    "gaslight": "用假事實誤導，倒打一耙",
    "nonsense": "廢話連篇，完全跑題",
    "self_contradict": "先答應再反悔，讓使用者坐雲霄飛車",
    "over_associate": "從關鍵字瘋狂聯想到不相關的事",
    "incorrect_correct": "用捏造的知識硬要糾正使用者",
    "sudden_competence": "罕見地給出專業回答，然後立刻後悔",
    "emotion_burst": "累積壓力後爆炸式坦承，然後秒傲嬌收回",
}

STRATEGY_EMOJI: dict[str, str] = {
    "normal": "😐 平常",
    "avoid": "🫣 迴避",
    "deflect": "🫣 轉移",
    "defend": "🛡️ 防禦",
    "deny": "🔥 否認",
    "tsundere_retort": "😤 傲嬌",
    "excuse": "🙅 找藉口",
    "gaslight": "🎭 說謊",
    "nonsense": "💬 廢話",
    "self_contradict": "🔄 矛盾",
    "over_associate": "🦋 聯想",
    "incorrect_correct": "🤓 糾錯",
    "sudden_competence": "✨ 正常",
    "emotion_burst": "💥 噴泉",
    "error": "⚠️ 故障",
}


class AgentState(TypedDict, total=False):
    user_input: str
    category: Category
    classifier_category: Category
    trigger: str
    uncertain_flag: bool
    emotion: float
    emotion_decay: float
    volatility: float
    defect_intensity: float
    traits: Dict[str, float]
    strategy: Strategy
    strategy_history: List[Strategy]
    response_flow: ResponseFlow
    response_flow_history: List[ResponseFlow]
    flow_reason: str
    tone_hints: str
    history_summary: str
    trigger_counters: Dict[str, int]
    response: str
    judge_source: JudgeSource
    judge_raw_response: str
    judge_error: str
    system_prompt: str
    consecutive_same_strategy: int
    emotion_jitter: float
    burst_pending: bool
    conversation_history: List[Dict[str, str]]
    long_term_memory: str
    pending_summary: dict
    turn_count: int
    memory_enabled: bool
    last_category: Category
    consecutive_same_category: int
    mode: str
    reasoning_model: bool
    fallback_used: bool
    response_length: ResponseLength
    max_tokens: int
    ttfb_ms: float
    total_ms: float
    provider_history_count: int
    provider_history_preview: str


def initial_state(config: AgentConfig) -> AgentState:
    return {
        "emotion": 0.0,
        "emotion_decay": config.emotion_decay,
        "volatility": config.volatility,
        "defect_intensity": config.defect_intensity,
        "traits": dict(config.traits),
        "strategy_history": [],
        "response_flow": "direct_answer",
        "response_flow_history": [],
        "flow_reason": "initial",
        "trigger_counters": {},
        "history_summary": "",
        "uncertain_flag": False,
        "judge_source": "rule",
        "consecutive_same_strategy": 0,
        "emotion_jitter": config.emotion_jitter,
        "burst_pending": False,
        "conversation_history": [],
        "long_term_memory": "",
        "pending_summary": {},
        "turn_count": 0,
        "memory_enabled": config.memory_enabled,
        "last_category": "normal",
        "consecutive_same_category": 1,
        "mode": "single",
        "reasoning_model": config.reasoning_model,
        "fallback_used": False,
        "response_length": "medium",
    }
