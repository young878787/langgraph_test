from __future__ import annotations

"""Canonical response-output parsing helpers.

Cleaning is intentionally structural: it removes reasoning/wrapper metadata but
does not use language, persona phrases, or line position to guess which answer
the model meant to return.
"""

import json
import re


def smart_truncate(text: str, max_tokens: int) -> str:
    """Truncate at a sentence or pause boundary when one is available."""
    if not text or len(text) <= max_tokens:
        return text

    sentence_end = re.compile(r"[。！？!?…~～]+")
    for match in reversed(list(sentence_end.finditer(text))):
        if match.end() <= max_tokens:
            return text[: match.end()].rstrip()

    pause = re.compile(r"[，,、；;：:）\)】」』》〉]")
    for match in reversed(list(pause.finditer(text))):
        if match.end() <= max_tokens:
            return text[: match.end()].rstrip()

    return text[:max_tokens].rstrip()


_JSON_RESPONSE_KEYS = ("final_answer", "response", "answer", "content", "text", "line")
_METADATA_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:"
    r"initial\s+reaction|refining\s+for\s+constraints|"
    r"(?:draft|attempt)\s*\d+\s*(?:notes?|metadata)|"
    r"traditional\s+chinese\s*\?|[^\n]{1,40}\s+included\?"
    r")\s*[:：]?\s*(?:yes|no)?\s*$",
    re.IGNORECASE,
)
_DRAFT_PREFIX = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\s*)?(?:draft|attempt)\s*\d+\s*[:：]\s*(?:\*\s*)?",
    re.IGNORECASE,
)


def _unwrap_known_json(text: str) -> str | None:
    """Unwrap a known response object; preserve unknown JSON structures."""
    candidate = text
    fence = re.fullmatch(r"\s*```(?:json|text)?\s*(.*?)\s*```\s*", text, re.DOTALL | re.IGNORECASE)
    if fence:
        candidate = fence.group(1).strip()

    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return None

    if isinstance(parsed, dict):
        for key in _JSON_RESPONSE_KEYS:
            value = parsed.get(key)
            if isinstance(value, str):
                return value.strip()
    # JSON may be consumed by a caller that expects its original schema.
    return candidate.strip()


def clean_response(raw_response: str, state: dict | None = None) -> str:
    """Remove structural model metadata while conservatively preserving text.

    ``state`` remains accepted for API compatibility, but response cleaning is
    deliberately independent of persona/routing state.
    """
    del state
    if not raw_response:
        return ""

    text = re.sub(r"<think\b[^>]*>.*?</think\s*>", "", raw_response, flags=re.DOTALL | re.IGNORECASE)
    text = text.strip()
    if not text:
        return ""

    json_result = _unwrap_known_json(text)
    if json_result is not None:
        return json_result

    # Markdown fences are wrappers only when they enclose the whole response.
    fence = re.fullmatch(r"\s*```(?:text|markdown)?\s*(.*?)\s*```\s*", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1)

    kept_lines: list[str] = []
    for raw_line in text.splitlines():
        if _METADATA_LINE.match(raw_line):
            continue
        line = _DRAFT_PREFIX.sub("", raw_line).rstrip()
        if re.fullmatch(r"\s*[-=]{3,}\s*", line):
            continue
        kept_lines.append(line)

    # Keep paragraphs and line ordering. Collapse only excessive blank space.
    result = "\n".join(kept_lines).strip()
    return re.sub(r"\n{3,}", "\n\n", result)


def is_valid_response(response: str, min_length: int = 5) -> bool:
    return bool(response and len(response.strip()) >= min_length)
