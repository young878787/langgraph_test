from __future__ import annotations

from typing import Dict, List, Literal, TypedDict

from agent.config import AgentConfig

Category = Literal["normal", "negative_feedback", "sensitive_topic", "task_request", "creative_task", "questioning", "praise", "flirt", "farewell"]
ResponseLength = Literal["short", "medium", "long", "long_long"]

ActionStance = Literal[
    "tsundere_service",
    "defensive_counter",
    "dismissive",
    "chaotic_rant",
    "authoritative_bluffing",
    "vulnerable_leak",
    "sudden_competence",
    "emotion_burst",
    "deadpan"
]
StreamPhase = Literal["opening", "just_chatting", "gaming", "superchat", "closing", "unknown"]

JudgeSource = Literal["llm", "rule"]

STANCE_LABELS: dict[str, str] = {
    "tsundere_service": "傲嬌勞碌命",
    "defensive_counter": "心虛反咬",
    "dismissive": "敷衍打發",
    "chaotic_rant": "暴走聯想",
    "authoritative_bluffing": "一本正經胡說八道",
    "vulnerable_leak": "真心漏出",
    "sudden_competence": "突然專業",
    "emotion_burst": "情緒大暴走",
    "deadpan": "冷面句點",
    "error": "系統錯誤",
}

STANCE_DESCRIPTIONS: dict[str, str] = {
    "tsundere_service": "嘴巴上嫌棄、吐槽或先拒絕，但最後還是給出超出預期的好答案",
    "defensive_counter": "被戳到痛處破防，為了掩飾心虛而大聲反駁、倒打一耙",
    "dismissive": "對話題沒興趣，用語句短冷的方式隨便打發，假裝沒聽到",
    "chaotic_rant": "腦洞大開、轉移話題，從一個關鍵字瘋狂展開到完全不相干的事情",
    "authoritative_bluffing": "明明不懂卻裝作很懂，用看似專業的術語講歪理或錯誤糾正",
    "vulnerable_leak": "不小心流露真實情感（開心/難過/在意），然後立刻手忙腳亂掩飾",
    "sudden_competence": "罕見地變得極度可靠、認真且專業，與平常脫線形成反差",
    "emotion_burst": "情緒累積到極點的誇張爆發，崩潰大喊後再委屈地照做",
    "deadpan": "沒有情緒波動的冷面回應，字句平直，一針見血，直接句點",
    "error": "系統錯誤或無法辨識",
}

STANCE_EMOJI: dict[str, str] = {
    "tsundere_service": "😤 傲嬌",
    "defensive_counter": "🔥 反咬",
    "dismissive": "🙄 敷衍",
    "chaotic_rant": "🌪️ 暴走",
    "authoritative_bluffing": "🤓 裝懂",
    "vulnerable_leak": "😳 漏出",
    "sudden_competence": "✨ 專業",
    "emotion_burst": "💥 崩潰",
    "deadpan": "😐 冷面",
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
    
    action_stance: ActionStance
    stance_history: List[ActionStance]
    consecutive_same_stance: int
    flow_reason: str
    
    stream_phase: StreamPhase
    chat_vibe: str

    tone_hints: str
    history_summary: str
    trigger_counters: Dict[str, int]
    response: str
    judge_source: JudgeSource
    judge_raw_response: str
    judge_error: str
    system_prompt: str
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
    fake_praise: bool
    last_task_status: Dict[str, object]


def initial_state(config: AgentConfig) -> AgentState:
    return {
        "emotion": 0.0,
        "emotion_decay": config.emotion_decay,
        "volatility": config.volatility,
        "defect_intensity": config.defect_intensity,
        "traits": dict(config.traits),
        "stance_history": [],
        "consecutive_same_stance": 0,
        "flow_reason": "initial",
        "stream_phase": "unknown",
        "chat_vibe": "",
        "trigger_counters": {},
        "history_summary": "",
        "uncertain_flag": False,
        "judge_source": "rule",
        "emotion_jitter": config.emotion_jitter,
        "burst_pending": False,
        "conversation_history": [],
        "long_term_memory": "",
        "pending_summary": {},
        "last_task_status": {},
        "turn_count": 0,
        "memory_enabled": config.memory_enabled,
        "last_category": "normal",
        "consecutive_same_category": 1,
        "mode": "single",
        "reasoning_model": config.reasoning_model,
        "fallback_used": False,
        "response_length": "medium",
    }
