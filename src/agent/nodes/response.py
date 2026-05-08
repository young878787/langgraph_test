from __future__ import annotations

from agent.config import AgentConfig
from agent.state import AgentState
from agent.llm.prompting import build_prompts
from agent.llm.providers import get_provider
from agent.llm.validators import is_on_strategy, fallback_response


def _safe_call(provider, system_prompt, user_prompt, temperature):
    try:
        return provider.generate(system_prompt, user_prompt, temperature)
    except Exception:
        return None


def _safe_call_with_history(provider, system_prompt, user_prompt, temperature, history):
    try:
        return provider.generate_with_history(system_prompt, user_prompt, temperature, history)
    except Exception:
        return None


def generate_response(state: AgentState, config: AgentConfig) -> AgentState:
    system_prompt, user_prompt = build_prompts(state)
    provider = get_provider(config)
    memory_enabled = state.get("memory_enabled", False)
    conversation_history = state.get("conversation_history", [])

    if memory_enabled and conversation_history:
        response = _safe_call_with_history(provider, system_prompt, user_prompt, config.temperature, conversation_history)
    else:
        response = _safe_call(provider, system_prompt, user_prompt, config.temperature)

    if not response or len(response.strip()) < 5:
        response = fallback_response(state)
    elif not is_on_strategy(state, response, config):
        if memory_enabled and conversation_history:
            response = _safe_call_with_history(provider, system_prompt, user_prompt, config.retry_temperature, conversation_history)
        else:
            response = _safe_call(provider, system_prompt, user_prompt, config.retry_temperature)
        if not response or len(response.strip()) < 5:
            response = fallback_response(state)
        elif not is_on_strategy(state, response, config):
            response = fallback_response(state)

    return {"response": response, "system_prompt": system_prompt}
