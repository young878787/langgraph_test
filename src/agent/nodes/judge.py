from __future__ import annotations

from agent.config import AgentConfig
from agent.state import AgentState
from agent.llm.judging import build_judge_prompts
from agent.llm.judge_validators import parse_judge_output, parse_judge_output_v2
from agent.llm.providers import get_provider
from agent.nodes.classifier import classify_input
from agent.nodes.defect import decide_defect_strategy
from agent.logger import log_error


_LLM_JUDGE_FAILURE_REPORTED = False


def _fmt_judge_raw(raw1: str | None, raw2: str | None) -> str:
    parts = []
    if raw1:
        parts.append(f"call1: {raw1[:200]}")
    else:
        parts.append("call1: (None)")
    if raw2 and raw2 != raw1:
        parts.append(f"call2: {raw2[:200]}")
    return " | ".join(parts)


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
        "classifier_category": classification.get("category", "normal"),
        "judge_raw_response": "",
        "judge_error": "",
    }


def _safe_llm_call(provider, system_prompt, user_prompt, temperature, max_output_tokens=None, json_mode=False) -> str | None:
    global _LLM_JUDGE_FAILURE_REPORTED
    try:
        if json_mode:
            return provider.generate_json(system_prompt, user_prompt, temperature, max_output_tokens)
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

    judge_error = ""
    raw1 = _safe_llm_call(provider, system_prompt, user_prompt, config.judge_temperature, config.judge_max_output_tokens, json_mode=True)
    decision, judge_error = parse_judge_output_v2(raw1 or "")
    if decision is None:
        raw2 = _safe_llm_call(provider, system_prompt, user_prompt, config.judge_temperature, config.judge_max_output_tokens, json_mode=True)
        decision, judge_error = parse_judge_output_v2(raw2 or "")

    if decision is None:
        result = _run_smart_fallback(state, config)
        result["judge_error"] = judge_error or "Judge LLM 連續兩次呼叫失敗 (API 錯誤或無效回應)"
        result["judge_raw_response"] = _fmt_judge_raw(raw1, raw2)
        return result

    category, strategy = decision

    emotion = state.get("emotion", 0.0)
    if emotion < -0.3 and strategy in ("over_associate", "nonsense"):
        strategy = "tsundere_retort" if state.get("traits", {}).get("tsundere", 0.0) >= 0.7 else "normal"

    return {
        "category": category,
        "classifier_category": base_classification.get("category", "normal"),
        "strategy": strategy,
        "trigger": base_classification.get("trigger", ""),
        "uncertain_flag": base_classification.get("uncertain_flag", False),
        "judge_source": "llm",
        "judge_raw_response": raw1 or "",
        "judge_error": "",
    }
