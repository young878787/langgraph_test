from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Dict, List, Tuple
from dotenv import load_dotenv

load_dotenv()

DEFAULT_SENSITIVE_TOPICS = [
    "appearance",
    "body",
    "small chest",
    "flat chest",
]

DEFAULT_NEGATIVE_FEEDBACK = [
    "bad",
    "wrong",
    "stupid",
    "fail",
    "ugly",
    "small",
    "笨蛋",
    "白痴",
    "廢物",
    "沒用",
    "爛",
    "差勁",
    "討厭",
]

DEFAULT_AVOID_MARKERS = [
    "let's talk about",
    "maybe we should change the topic",
    "i would rather not discuss",
    "can we talk about something else",
]

DEFAULT_TASK_REQUEST_KEYWORDS = [
    "幫我",
    "請幫",
    "我要",
    "可以幫",
    "幫忙",
    "啟動",
    "執行",
    "創建",
    "寫一個",
    "寫個",
    "做一個",
    "help me",
    "please do",
    "can you",
    "generate",
    "create",
    "write",
    "make",
]

DEFAULT_QUESTIONING_KEYWORDS = [
    "你能幹嗎",
    "你真的會",
    "你懂嗎",
    "你不是真的",
    "你假装",
    "你謊言",
    "你按照眺本",
    "你不能",
    "你并不會",
    "are you sure",
    "you don't actually",
    "you're just",
    "prove it",
]


@dataclass
class AgentConfig:
    sensitive_topics: List[str] = field(default_factory=lambda: DEFAULT_SENSITIVE_TOPICS.copy())
    negative_feedback: List[str] = field(default_factory=lambda: DEFAULT_NEGATIVE_FEEDBACK.copy())
    avoid_markers: List[str] = field(default_factory=lambda: DEFAULT_AVOID_MARKERS.copy())
    task_request_keywords: List[str] = field(
        default_factory=lambda: DEFAULT_TASK_REQUEST_KEYWORDS.copy()
    )
    questioning_keywords: List[str] = field(
        default_factory=lambda: DEFAULT_QUESTIONING_KEYWORDS.copy()
    )
    emotion_bounds: Tuple[float, float] = (-1.0, 1.0)
    emotion_decay: float = 0.05
    volatility: float = 0.75
    defect_intensity: float = 0.85
    traits: Dict[str, float] = field(
        default_factory=lambda: {
            "tsundere": 0.85,
            "yandere": 0.4,
            "excuse_prone": 0.75,
            "liar": 0.7,
            "rambler": 0.6,
            "contradict_prone": 0.65,
            "overthinker": 0.7,
            "knowitall": 0.55,
            "perfectionist": 0.3,
        }
    )
    backend: str = field(default_factory=lambda: os.getenv("LLM_BACKEND", "mock"))
    openrouter_model: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    )
    google_model: str = field(
        default_factory=lambda: os.getenv("GOOGLE_MODEL", "gemma-4-31b-it")
    )
    temperature: float = 0.85
    retry_temperature: float = 0.3
    emotion_jitter: float = 0.10
    streaming_enabled: bool = True
    burst_threshold: int = 3
