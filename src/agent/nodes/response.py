from __future__ import annotations

from agent.config import AgentConfig
from agent.state import AgentState
from agent.llm.prompting import build_prompts
from agent.llm.providers import get_provider
from agent.llm.validators import is_on_strategy, fallback_response


def generate_response(state: AgentState, config: AgentConfig) -> AgentState:
    system_prompt, user_prompt = build_prompts(state)
    provider = get_provider(config)

    # 第一次嘗試
    response = provider.generate(system_prompt, user_prompt, config.temperature)
    
    # 檢查回應是否有效
    if not response or len(response.strip()) < 5:
        response = fallback_response(state)
    elif not is_on_strategy(state, response, config):
        # 第二次嘗試，使用較低溫度
        response = provider.generate(system_prompt, user_prompt, config.retry_temperature)
        if not response or len(response.strip()) < 5:
            response = fallback_response(state)
        elif not is_on_strategy(state, response, config):
            response = fallback_response(state)

    return {"response": response}
