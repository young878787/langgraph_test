from __future__ import annotations

import time
import json
import re

from agent.config import AgentConfig
from agent.state import AgentState
from agent.llm.prompting import build_prompts, format_provider_history_preview
from agent.llm.providers import get_provider
from agent.llm.validators import finalize_response
from agent.llm.output_parser import smart_truncate
from agent.logger import log_error


_LLM_FAILURE_REPORTED: set = set()


def _safe_call(provider, system_prompt, user_prompt, temperature, max_output_tokens=None):
    try:
        return provider.generate(system_prompt, user_prompt, temperature, max_output_tokens)
    except Exception as e:
        key = "generate"
        if key not in _LLM_FAILURE_REPORTED:
            _LLM_FAILURE_REPORTED.add(key)
            log_error("response", "_safe_call", e, {"backend": type(provider).__name__})
        return None


def _safe_call_with_history(provider, system_prompt, user_prompt, temperature, history, max_output_tokens=None):
    try:
        return provider.generate_with_history(system_prompt, user_prompt, temperature, history, max_output_tokens)
    except Exception as e:
        key = "generate_with_history"
        if key not in _LLM_FAILURE_REPORTED:
            _LLM_FAILURE_REPORTED.add(key)
            log_error("response", "_safe_call_with_history", e, {"backend": type(provider).__name__})
        return None

def coerce_plain_response(text: str) -> str:
    """Keep response LLM as plain text while tolerating legacy JSON-shaped output."""
    if not text:
        return ""

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json|text)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except Exception:
        data = None

    if isinstance(data, dict):
        line = data.get("line")
        if isinstance(line, str):
            return line.strip()

    match = re.search(r'"line"\s*:\s*"((?:\\.|[^"\\])*)"', text)
    if match:
        try:
            return match.group(1).encode().decode('unicode_escape')
        except Exception:
            return match.group(1)

    cleaned = re.sub(r'^.*?("line"\s*:\s*|line\s*:)', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^[{"\s]*', '', cleaned)
    cleaned = re.sub(r'["}, \s]*$', '', cleaned)
    return cleaned


def generate_response(state: AgentState, config: AgentConfig) -> AgentState:
    t_start = time.perf_counter()
    system_prompt, user_prompt = build_prompts(state)
    provider = get_provider(config)
    memory_enabled = state.get("memory_enabled", False)
    conversation_history = state.get("conversation_history", [])
    provider_history = conversation_history if memory_enabled else []
    provider_history_count = len(provider_history)
    provider_history_preview = format_provider_history_preview(provider_history)

    response_length = state.get("response_length", "medium")
    if response_length == "long":
        temperature = config.verbose_temperature
        max_output_tokens = config.long_max_tokens
    elif response_length == "long_long":
        temperature = config.verbose_temperature
        max_output_tokens = config.long_long_max_tokens
    elif response_length == "short":
        temperature = 0.75
        max_output_tokens = config.short_max_tokens
    else:
        temperature = config.temperature
        max_output_tokens = config.medium_max_tokens

    if memory_enabled and conversation_history:
        raw_response = _safe_call_with_history(
            provider,
            system_prompt,
            user_prompt,
            temperature,
            conversation_history,
            max_output_tokens,
        )
    else:
        raw_response = _safe_call(provider, system_prompt, user_prompt, temperature, max_output_tokens)

    if raw_response:
        response = coerce_plain_response(raw_response)
        response = smart_truncate(response, max_output_tokens)
    else:
        response = ""

    def _retry(correction: str) -> str:
        retry_prompt = f"{user_prompt}\n\nCorrective instruction: {correction}"
        if memory_enabled and conversation_history:
            retry_raw = _safe_call_with_history(provider, system_prompt, retry_prompt, temperature, conversation_history, max_output_tokens)
        else:
            retry_raw = _safe_call(provider, system_prompt, retry_prompt, temperature, max_output_tokens)
        if not retry_raw:
            return ""
        return smart_truncate(coerce_plain_response(retry_raw), max_output_tokens)

    finalized = finalize_response(state, response, config, retry=_retry)
    response = finalized.response
    if finalized.raw_retry_response:
        raw_response = finalized.raw_retry_response

    total_ms = (time.perf_counter() - t_start) * 1000

    return {
        "response": response,
        "system_prompt": system_prompt,
        "fallback_used": bool(finalized.fallback_reason),
        "response_validation": {
            "valid": finalized.validation.valid,
            "reason": finalized.validation.reason,
            "rejection_reason": finalized.rejection_reason,
            "retry_count": finalized.retry_count,
            "fallback_reason": finalized.fallback_reason,
            "fallback_template_id": finalized.fallback_template_id,
            "style_score": finalized.style.score,
            "style_signals": list(finalized.style.signals),
        },
        "max_tokens": max_output_tokens,
        "ttfb_ms": None,
        "total_ms": total_ms,
        "provider_history_count": provider_history_count,
        "provider_history_preview": provider_history_preview,
        "raw_llm_response": raw_response if raw_response else "",
    }
