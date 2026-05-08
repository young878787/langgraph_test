from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Turn:
    role: str
    content: str


@dataclass
class ConversationMemory:
    max_turns: int = 10
    summary_interval: int = 5
    turns: List[Turn] = field(default_factory=list)
    long_term_summary: str = ""

    def add(self, user_input: str, ai_response: str) -> None:
        self.turns.append(Turn(role="user", content=user_input))
        self.turns.append(Turn(role="assistant", content=ai_response))

        if len(self.turns) > self.max_turns * 2:
            to_summarize = self.turns[:-(self.max_turns * 2)]
            self.turns = self.turns[-(self.max_turns * 2):]
            self._compact(to_summarize)

    def _compact(self, old_turns: List[Turn]) -> None:
        lines = []
        for t in old_turns:
            role = "使用者" if t.role == "user" else "AI"
            lines.append(f"[{role}]: {t.content[:80]}")
        new_summary = "、".join(lines)

        if self.long_term_summary:
            self.long_term_summary = (
                f"{self.long_term_summary}；更早前：{new_summary}"
            )
        else:
            self.long_term_summary = f"先前對話摘要：{new_summary}"

        if len(self.long_term_summary) > 600:
            self.long_term_summary = self.long_term_summary[-600:]

    @property
    def turn_count(self) -> int:
        return len([t for t in self.turns if t.role == "user"])

    @property
    def last_user_input(self) -> str:
        for t in reversed(self.turns):
            if t.role == "user":
                return t.content
        return ""

    @property
    def last_ai_response(self) -> str:
        for t in reversed(self.turns):
            if t.role == "assistant":
                return t.content
        return ""

    def get_context_text(self, include_summary: bool = True) -> str:
        lines = []
        if include_summary and self.long_term_summary:
            lines.append(self.long_term_summary)
            lines.append("---")
        for t in self.turns:
            role = "🧑 使用者" if t.role == "user" else "🤖 AI"
            lines.append(f"{role}: {t.content}")
        return "\n".join(lines)

    def to_gemini_contents(self, current_user_input: Optional[str] = None):
        from google.genai import types

        parts = []
        for t in self.turns:
            if t.role == "user":
                parts.append(types.Part(text=t.content))
            else:
                parts.append(types.Part(text=t.content))

        contents = []
        i = 0
        while i < len(self.turns):
            user_turn = self.turns[i] if self.turns[i].role == "user" else None
            model_turn = self.turns[i + 1] if i + 1 < len(self.turns) and self.turns[i + 1].role == "assistant" else None

            if user_turn and model_turn:
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part(text=user_turn.content)],
                    )
                )
                contents.append(
                    types.Content(
                        role="model",
                        parts=[types.Part(text=model_turn.content)],
                    )
                )
                i += 2
            elif user_turn:
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part(text=user_turn.content)],
                    )
                )
                i += 1
            else:
                contents.append(
                    types.Content(
                        role="model",
                        parts=[types.Part(text=self.turns[i].content)],
                    )
                )
                i += 1

        if current_user_input:
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=current_user_input)],
                )
            )

        return contents

    def to_dict(self) -> dict:
        return {
            "turns": [{"role": t.role, "content": t.content} for t in self.turns],
            "long_term_summary": self.long_term_summary,
            "max_turns": self.max_turns,
            "summary_interval": self.summary_interval,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ConversationMemory:
        mem = cls(
            max_turns=data.get("max_turns", 10),
            summary_interval=data.get("summary_interval", 5),
        )
        mem.turns = [Turn(role=t["role"], content=t["content"]) for t in data.get("turns", [])]
        mem.long_term_summary = data.get("long_term_summary", "")
        return mem
