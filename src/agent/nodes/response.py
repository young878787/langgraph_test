from __future__ import annotations

from agent.config import AgentConfig
from agent.state import AgentState
from agent.llm.prompting import build_prompts
from agent.llm.providers import get_provider
from agent.llm.validators import is_on_strategy, fallback_response


def generate_response(state: AgentState, config: AgentConfig) -> AgentState:
    system_prompt, user_prompt = build_prompts(state)
    provider = get_provider(config)

    response = provider.generate(system_prompt, user_prompt, config.temperature)
    if not is_on_strategy(state, response, config):
        response = provider.generate(system_prompt, user_prompt, config.retry_temperature)
        if not is_on_strategy(state, response, config):
            response = fallback_response(state)

    return {"response": response}
