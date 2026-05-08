from __future__ import annotations

from agent.config import AgentConfig
from agent.state import AgentState
from agent.llm.judging import build_judge_prompts
from agent.llm.judge_validators import parse_judge_output
from agent.llm.providers import get_provider
from agent.nodes.classifier import classify_input
from agent.nodes.defect import decide_defect_strategy
from agent.logger import log_error


def _run_rule_fallback(state: AgentState, config: AgentConfig) -> AgentState:
    classification = classify_input(state, config)
    merged_state: AgentState = {**state, **classification}
    strategy = decide_defect_strategy(merged_state, config)

    return {
        **classification,
        **strategy,
        "judge_source": "rule",
    }


def _safe_llm_call(provider, system_prompt, user_prompt, temperature) -> str | None:
    try:
        return provider.generate(system_prompt, user_prompt, temperature)
    except Exception:
        return None


def judge_input(state: AgentState, config: AgentConfig) -> AgentState:
    base_classification = classify_input(state, config)

    system_prompt, user_prompt = build_judge_prompts(state)
    provider = get_provider(config)

    response = _safe_llm_call(provider, system_prompt, user_prompt, config.temperature)
    decision = parse_judge_output(response or "")
    if decision is None:
        response = _safe_llm_call(provider, system_prompt, user_prompt, config.retry_temperature)
        decision = parse_judge_output(response or "")

    if decision is None:
        return _run_rule_fallback(state, config)

    category, strategy = decision

    mode_mapping = {
        "avoid": "avoidance",
        "deflect": "avoidance",
        "deny": "angry_denial",
        "tsundere_retort": "tsundere",
        "defend": "defend",
        "excuse": "excuse",
        "gaslight": "gaslight",
        "nonsense": "rambling",
        "normal": "cooperative_for_once",
        "self_contradict": "self_contradict",
        "over_associate": "over_associate",
        "incorrect_correct": "incorrect_correct",
        "sudden_competence": "sudden_competence",
        "emotion_burst": "burst",
    }
    defect_mode = mode_mapping.get(strategy, "none")

    return {
        "category": category,
        "strategy": strategy,
        "trigger": base_classification.get("trigger", ""),
        "uncertain_flag": base_classification.get("uncertain_flag", False),
        "defect_mode": defect_mode,
        "judge_source": "llm",
    }
