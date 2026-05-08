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
    "excuse",
    "gaslight",
    "nonsense",
    "self_contradict",
    "over_associate",
    "incorrect_correct",
    "sudden_competence",
    "emotion_burst",
]
Tone = Literal[
    "normal", "tsundere", "yandere", "avoidance", "excuse", "gaslight", "nonsense",
    "contradict", "overthink", "knowitall", "perfectionist", "burst",
]
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
    defect_mode: str
    system_prompt: str
    consecutive_same_strategy: int
    emotion_jitter: float
    burst_pending: bool
    conversation_history: List[Dict[str, str]]
    turn_count: int
    memory_enabled: bool
    mode: str


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
        "consecutive_same_strategy": 0,
        "emotion_jitter": config.emotion_jitter,
        "burst_pending": False,
        "conversation_history": [],
        "turn_count": 0,
        "memory_enabled": config.memory_enabled,
        "mode": "single",
    }
