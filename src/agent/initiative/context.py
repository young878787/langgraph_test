"""Bounded, provenance-aware context construction for initiative stages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any


_DENIED_KEY_PARTS = (
    "debug",
    "fakeclock",
    "random_score",
    "candidate_score",
    "raw_score",
    "score",
    "runner",
    "timer",
    "schedule",
)
_ALLOWED_MODES = {"conversation_followup", "topic_discovery"}
_ALLOWED_ROLES = {"user", "assistant"}


def _is_denied_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(part in lowered for part in _DENIED_KEY_PARTS)


def _safe_value(value: Any, *, depth: int = 0) -> Any:
    """Copy JSON-like values while removing internal/debug-shaped fields."""
    if depth > 4:
        return None
    if isinstance(value, Mapping):
        return {
            str(key): _safe_value(item, depth=depth + 1)
            for key, item in value.items()
            if not _is_denied_key(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, depth=depth + 1) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _text_tokens(value: Any) -> set[str]:
    """Extract small, case-folded tokens used for deterministic relevance."""
    if isinstance(value, str):
        text = value.casefold()
        tokens = {token for token in re.findall(r"[a-z0-9_]+", text) if len(token) >= 2}
        for run in re.findall(r"[\u4e00-\u9fff]+", text):
            tokens.add(run)
            tokens.update(run[index : index + 2] for index in range(len(run) - 1))
        return tokens
    if isinstance(value, Mapping):
        tokens: set[str] = set()
        for key, item in value.items():
            if not _is_denied_key(str(key)):
                tokens.update(_text_tokens(item))
        return tokens
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        tokens: set[str] = set()
        for item in value:
            tokens.update(_text_tokens(item))
        return tokens
    return set()


def _normalise_history(history: Any) -> list[dict[str, str]]:
    """Keep only real conversation turns with supported roles and text."""
    if not isinstance(history, Sequence) or isinstance(history, (str, bytes)):
        return []
    normalised: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role", "")).casefold()
        content = item.get("content")
        if role not in _ALLOWED_ROLES or not isinstance(content, str) or not content.strip():
            continue
        normalised.append({"role": role, "content": content.strip()})
    return normalised


def _select_excerpt(
    history: list[dict[str, str]],
    candidate_goal_context: Any,
    open_thread: Any,
    max_items: int,
    max_chars: int,
) -> list[dict[str, str]]:
    """Select relevant turns and one neighbouring turn for necessary context."""
    if not history:
        return []
    tokens = _text_tokens(candidate_goal_context) | _text_tokens(open_thread)
    user_indices = [index for index, item in enumerate(history) if item["role"] == "user"]
    if user_indices:
        tokens |= _text_tokens(history[user_indices[-1]]["content"])

    scored: list[tuple[int, int]] = []
    for index, item in enumerate(history):
        item_tokens = _text_tokens(item["content"])
        relevance = len(tokens & item_tokens)
        if item["role"] == "user" and index == user_indices[-1]:
            relevance += 2
        if relevance:
            scored.append((relevance, index))
    if not scored:
        selected = list(range(max(0, len(history) - min(max_items, 2)), len(history)))
    else:
        selected_indices: set[int] = set()
        for _, index in sorted(scored, key=lambda pair: (-pair[0], -pair[1]))[:max_items]:
            selected_indices.add(index)
            if index > 0:
                selected_indices.add(index - 1)
        selected = sorted(selected_indices)[-max_items:]

    excerpt: list[dict[str, str]] = []
    remaining = max_chars
    for index in selected:
        item = history[index]
        content = item["content"][:remaining]
        if not content:
            break
        excerpt.append({"role": item["role"], "content": content})
        remaining -= len(content)
    return excerpt


def _source_refs(
    excerpt: list[dict[str, str]],
    memory_summary: str,
    open_thread: Any,
    relationship_context: Any,
    character_state_summary: Any,
    evidence_refs: Any,
) -> list[str]:
    """Build stable evidence references without exposing internal execution data."""
    refs: list[str] = []
    if any(item["role"] == "user" for item in excerpt):
        refs.append("dialogue:last_user")
        refs.extend(f"dialogue:{item['role']}:{index}" for index, item in enumerate(excerpt))
    if memory_summary.strip():
        refs.append("memory:long_term")
    if open_thread:
        refs.append("open_thread")
    if relationship_context:
        refs.append("state:relationship")
    if character_state_summary:
        refs.append("state:character")
    if isinstance(evidence_refs, Sequence) and not isinstance(evidence_refs, (str, bytes)):
        refs.extend(str(ref) for ref in evidence_refs if isinstance(ref, str) and ref.strip())
    return list(dict.fromkeys(refs))


def build_context(
    *,
    mode: str | None = None,
    conversation_history: Any = None,
    long_term_memory: Any = "",
    open_thread: Any = None,
    relationship_context: Any = None,
    character_state_summary: Any = None,
    candidate_goal_context: Any = None,
    evidence_refs: Any = None,
    state: Mapping[str, Any] | None = None,
    max_excerpt_items: int = 8,
    max_excerpt_chars: int = 2400,
) -> dict[str, Any]:
    """Build the bounded context payload consumed by Planner and Generator prompts."""
    state = state or {}
    if conversation_history is None:
        conversation_history = state.get("conversation_history", [])
    if not long_term_memory:
        long_term_memory = state.get("long_term_memory", "")
    if open_thread is None:
        open_thread = state.get("open_thread", {})
    if relationship_context is None:
        relationship_context = state.get("relationship_state", {})
    if character_state_summary is None:
        character_state_summary = state.get("character_state", {})
    if candidate_goal_context is None:
        candidate_goal_context = state.get("candidate_goal_context", {})

    history = _normalise_history(conversation_history)
    selected_mode = mode or ("conversation_followup" if history else "topic_discovery")
    if selected_mode not in _ALLOWED_MODES:
        raise ValueError(f"unsupported initiative context mode: {selected_mode}")
    excerpt = (
        _select_excerpt(history, candidate_goal_context, open_thread, max_excerpt_items, max_excerpt_chars)
        if selected_mode == "conversation_followup"
        else []
    )
    memory = long_term_memory.strip() if isinstance(long_term_memory, str) else str(long_term_memory or "")
    memory = "\n".join(
        line
        for line in memory.splitlines()
        if not any(part in line.casefold().replace("-", "_") for part in _DENIED_KEY_PARTS)
    )
    safe_relationship = _safe_value(relationship_context) or {}
    safe_character = _safe_value(character_state_summary) or {}
    safe_goal = _safe_value(candidate_goal_context) or {}
    safe_open_thread = _safe_value(open_thread) or {}
    return {
        "mode": selected_mode,
        "conversation_excerpt": excerpt,
        "memory_summary": memory[:4000],
        "open_thread": safe_open_thread,
        "relationship_context": safe_relationship,
        "character_state_summary": safe_character,
        "candidate_goal_context": safe_goal,
        "evidence_refs": _source_refs(
            excerpt,
            memory,
            safe_open_thread,
            safe_relationship,
            safe_character,
            evidence_refs,
        ),
    }


class ContextBuilder:
    """Reusable context builder with bounded excerpt limits."""

    def __init__(self, *, max_excerpt_items: int = 8, max_excerpt_chars: int = 2400) -> None:
        self.max_excerpt_items = max_excerpt_items
        self.max_excerpt_chars = max_excerpt_chars

    def build(self, **kwargs: Any) -> dict[str, Any]:
        """Build context using this builder's configured bounds."""
        kwargs.setdefault("max_excerpt_items", self.max_excerpt_items)
        kwargs.setdefault("max_excerpt_chars", self.max_excerpt_chars)
        return build_context(**kwargs)
