from __future__ import annotations

import time

from agent.config import AgentConfig
from agent.state import AgentState
from agent.llm.prompting import build_prompts, format_provider_history_preview
from agent.llm.providers import get_provider
from agent.llm.validators import is_on_strategy, fallback_response
from agent.llm.output_parser import smart_truncate
from agent.llm.judge_validators import _extract_json
import json
from agent.llm.judge_validators import _extract_json
import json
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

def _parse_response_json(raw_text: str) -> tuple[str, dict]:
    if not raw_text:
        return "", {}
    
    extracted = _extract_json(raw_text)
    if not extracted:
        return raw_text.strip(), {}
        
    try:
        data = json.loads(extracted)
        return data.get("line", raw_text).strip(), data
    except Exception:
        return raw_text.strip(), {}


def generate_response(state: AgentState, config: AgentConfig) -> AgentState:
    t_start = time.perf_counter()
    system_prompt, user_prompt = build_prompts(state)
    provider = get_provider(config)
    memory_enabled = state.get("memory_enabled", False)
    conversation_history = state.get("conversation_history", [])
    provider_history = conversation_history if memory_enabled else []
    provider_history_count = len(provider_history)
    provider_history_preview = format_provider_history_preview(provider_history)
    fallback_used = False

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

    min_len = {"short": 2, "medium": 5, "long": 20, "long_long": 30}.get(response_length, 5)
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

    response_meta = {}
    if raw_response:
        response, response_meta = _parse_response_json(raw_response)
        response = smart_truncate(response, max_output_tokens)
    else:
        response = ""

    if not response or len(response.strip()) < min_len:
        response = fallback_response(state)
        fallback_used = True
    elif not is_on_strategy(state, response, config):
        if memory_enabled and conversation_history:
            raw_response = _safe_call_with_history(provider, system_prompt, user_prompt, config.retry_temperature, conversation_history, max_output_tokens)
        else:
            raw_response = _safe_call(provider, system_prompt, user_prompt, config.retry_temperature, max_output_tokens)
            
        if raw_response:
            response, response_meta = _parse_response_json(raw_response)
            response = smart_truncate(response, max_output_tokens)
            
        if not response or len(response.strip()) < min_len:
            response = fallback_response(state)
            fallback_used = True
        elif not is_on_strategy(state, response, config):
            response = fallback_response(state)
            fallback_used = True

    # ==========================
    # VTuber Output JSON Parsing
    # ==========================
    if fallback_used:
        chosen_strategy = "fallback"
    else:
        chosen_strategy = response_meta.get("chosen_strategy", "fallback/parsing_error") if response_meta else "fallback/parsing_error"

    total_ms = (time.perf_counter() - t_start) * 1000
    
    # Store performance metadata back into state
    perf_output = state.get("performance_output", {})
    if response_meta:
        perf_output["llm_meta"] = response_meta

    return {
        "response": response,
        "system_prompt": system_prompt,
        "fallback_used": fallback_used,
        "max_tokens": max_output_tokens,
        "ttfb_ms": None,
        "total_ms": total_ms,
        "provider_history_count": provider_history_count,
        "provider_history_preview": provider_history_preview,
        "performance_output": perf_output,
        "raw_llm_response": raw_response if raw_response else "",
        "flow_reason": f"{state.get('flow_reason', '')} | chosen_strategy={chosen_strategy}"
    }
