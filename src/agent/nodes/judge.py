from __future__ import annotations

from agent.config import AgentConfig
from agent.state import AgentState
from agent.llm.judging import build_judge_prompts
from agent.llm.judge_validators import parse_judge_output
from agent.llm.providers import get_provider
from agent.nodes.classifier import classify_input
from agent.nodes.defect import decide_defect_strategy
from agent.logger import log_error


_LLM_JUDGE_FAILURE_REPORTED = False


def _run_smart_fallback(state: AgentState, config: AgentConfig) -> AgentState:
    classification = classify_input(state, config)
    merged_state: AgentState = {**state, **classification}
    strategy = decide_defect_strategy(merged_state, config)
    category = classification.get("category", "normal")
    chosen_strategy = strategy.get("strategy", "normal")

    emotion = state.get("emotion", 0.0)
    if category == "flirt" or category == "praise":
        chosen_strategy = "tsundere_retort"
        strategy["strategy"] = chosen_strategy

    if emotion < -0.3 and chosen_strategy in ("over_associate", "nonsense"):
        chosen_strategy = "tsundere_retort" if state.get("traits", {}).get("tsundere", 0.0) >= 0.7 else "normal"
        strategy["strategy"] = chosen_strategy

    return {
        **classification,
        **strategy,
        "judge_source": "rule",
    }


def _safe_llm_call(provider, system_prompt, user_prompt, temperature, max_output_tokens=None) -> str | None:
    global _LLM_JUDGE_FAILURE_REPORTED
    try:
        return provider.generate(system_prompt, user_prompt, temperature, max_output_tokens)
    except Exception as e:
        if not _LLM_JUDGE_FAILURE_REPORTED:
            _LLM_JUDGE_FAILURE_REPORTED = True
            log_error("judge", "_safe_llm_call", e, {"backend": type(provider).__name__})
        return None


def judge_input(state: AgentState, config: AgentConfig) -> AgentState:
    base_classification = classify_input(state, config)

    system_prompt, user_prompt = build_judge_prompts(state)
    provider = get_provider(config)

    response = _safe_llm_call(provider, system_prompt, user_prompt, config.temperature, config.judge_max_output_tokens)
    decision = parse_judge_output(response or "")
    if decision is None:
        response = _safe_llm_call(provider, system_prompt, user_prompt, config.retry_temperature, config.judge_max_output_tokens)
        decision = parse_judge_output(response or "")

    if decision is None:
        return _run_smart_fallback(state, config)

    category, strategy = decision

    emotion = state.get("emotion", 0.0)
    if emotion < -0.3 and strategy in ("over_associate", "nonsense"):
        strategy = "tsundere_retort" if state.get("traits", {}).get("tsundere", 0.0) >= 0.7 else "normal"

    return {
        "category": category,
        "strategy": strategy,
        "trigger": base_classification.get("trigger", ""),
        "uncertain_flag": base_classification.get("uncertain_flag", False),
        "judge_source": "llm",
    }
