from __future__ import annotations

from agent.config import AgentConfig
from agent.state import AgentState
from agent.llm.prompting import build_prompts
from agent.llm.providers import get_provider
from agent.llm.validators import is_on_strategy, fallback_response
from agent.logger import log_error


_LLM_FAILURE_REPORTED: set = set()


def _safe_call(provider, system_prompt, user_prompt, temperature):
    try:
        return provider.generate(system_prompt, user_prompt, temperature)
    except Exception as e:
        key = "generate"
        if key not in _LLM_FAILURE_REPORTED:
            _LLM_FAILURE_REPORTED.add(key)
            log_error("response", "_safe_call", e, {"backend": type(provider).__name__})
        return None


def _safe_call_with_history(provider, system_prompt, user_prompt, temperature, history):
    try:
        return provider.generate_with_history(system_prompt, user_prompt, temperature, history)
    except Exception as e:
        key = "generate_with_history"
        if key not in _LLM_FAILURE_REPORTED:
            _LLM_FAILURE_REPORTED.add(key)
            log_error("response", "_safe_call_with_history", e, {"backend": type(provider).__name__})
        return None


def generate_response(state: AgentState, config: AgentConfig) -> AgentState:
    system_prompt, user_prompt = build_prompts(state)
    provider = get_provider(config)
    memory_enabled = state.get("memory_enabled", False)
    conversation_history = state.get("conversation_history", [])
    fallback_used = False

    response_length = state.get("response_length", "medium")
    if response_length == "long":
        temperature = config.verbose_temperature
    elif response_length == "short":
        temperature = 0.75
    else:
        temperature = config.temperature

    if memory_enabled and conversation_history:
        response = _safe_call_with_history(provider, system_prompt, user_prompt, temperature, conversation_history)
    else:
        response = _safe_call(provider, system_prompt, user_prompt, temperature)

    min_len = {"short": 2, "medium": 5, "long": 20}.get(response_length, 5)
    if not response or len(response.strip()) < min_len:
        response = fallback_response(state)
        fallback_used = True
    elif not is_on_strategy(state, response, config):
        if memory_enabled and conversation_history:
            response = _safe_call_with_history(provider, system_prompt, user_prompt, config.retry_temperature, conversation_history)
        else:
            response = _safe_call(provider, system_prompt, user_prompt, config.retry_temperature)
        if not response or len(response.strip()) < min_len:
            response = fallback_response(state)
            fallback_used = True
        elif not is_on_strategy(state, response, config):
            response = fallback_response(state)
            fallback_used = True

    return {"response": response, "system_prompt": system_prompt, "fallback_used": fallback_used}
