from __future__ import annotations

from typing import Dict, List, Literal, TypedDict

from agent.config import AgentConfig

Category = Literal["normal", "negative_feedback", "sensitive_topic", "task_request", "questioning"]
Strategy = Literal[
    "normal",
    "avoid",
    "deflect",
    "defend",
    "deny",
    "tsundere_retort",
    "excuse",        # 找藉口：怪罪外部、裝忙、死不認錯
    "gaslight",      # 說謊：扭曲事實、一本正經胡說
    "nonsense",      # 廢話連篇：跑題、哲學、AI 夢境
]
Tone = Literal["normal", "tsundere", "yandere", "avoidance", "excuse", "gaslight", "nonsense"]
JudgeSource = Literal["llm", "rule"]


class AgentState(TypedDict, total=False):
    user_input: str
    category: Category
    trigger: str
    uncertain_flag: bool
    emotion: float
    emotion_decay: float
    volatility: float
    defect_intensity: float
    traits: Dict[str, float]
    strategy: Strategy
    strategy_history: List[Strategy]
    tone: Tone
    tone_hints: str
    history_summary: str
    trigger_counters: Dict[str, int]
    response: str
    judge_source: JudgeSource
    # 搞笑缺陷模式：記錄本輪觸發了哪種缺陷模式以便 debug
    defect_mode: str


def initial_state(config: AgentConfig) -> AgentState:
    return {
        "emotion": 0.0,
        "emotion_decay": config.emotion_decay,
        "volatility": config.volatility,
        "defect_intensity": config.defect_intensity,
        "traits": dict(config.traits),
        "strategy_history": [],
        "trigger_counters": {},
        "history_summary": "",
        "uncertain_flag": False,
        "judge_source": "rule",
    }
