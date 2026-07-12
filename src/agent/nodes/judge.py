from __future__ import annotations

from agent.config import AgentConfig
from agent.state import AgentState
from agent.llm.judging import build_judge_prompts
from agent.llm.judge_validators import build_rule_event_analysis, parse_judge_output_v2
from agent.llm.providers import get_provider
from agent.nodes.classifier import classify_input
from agent.logger import log_error
from agent.task_status import is_fake_praise_for_unproduced_task

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


def _check_fake_praise(state: AgentState) -> bool:
    if is_fake_praise_for_unproduced_task(state):
        return True

    conv_hist = state.get("conversation_history", [])
    if len(conv_hist) < 2:
        return False

    refuse_markers = ("靈感", "沒心情", "不想", "不做", "不幫", "沒有", "拒絕", "不寫", "不畫")
    request_markers = ("幫我", "寫", "翻譯", "畫", "做", "教", "給", "告訴")

    last_ai = conv_hist[-1]
    if last_ai.get("role") != "assistant":
        return False
    prev_user = conv_hist[-2]
    if prev_user.get("role") != "user":
        return False

    ai_msg = last_ai.get("content", "")
    user_msg = prev_user.get("content", "")
    return any(m in user_msg for m in request_markers) and any(m in ai_msg for m in refuse_markers)


def _run_smart_fallback(state: AgentState, config: AgentConfig) -> AgentState:
    classification = classify_input(state, config)
    category = classification.get("category", "normal")

    fake_praise = _check_fake_praise(state)
    if fake_praise:
        category = "questioning"

    requires_action = category in ("task_request", "creative_task")
    event_analysis = build_rule_event_analysis(category)
    event_analysis["ambiguous_flag"] = bool(classification.get("ambiguous_flag")) or fake_praise
    event_analysis["requires_action"] = requires_action

    return {
        **classification,
        "category": category,
        "judge_source": "rule",
        "classifier_category": classification.get("category", "normal"),
        "judge_raw_response": "",
        "judge_error": "",
        "fake_praise": fake_praise,
        "ambiguous_flag": bool(classification.get("ambiguous_flag")) or fake_praise,
        "sarcasm_possible": False,
        "requires_action": requires_action,
        "intent_target": "assistant" if category != "normal" else "unknown",
        "event_analysis": event_analysis,
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
    judge_state = {**state, **base_classification}

    system_prompt, user_prompt = build_judge_prompts(judge_state)
    provider = get_provider(config)

    judge_error = ""
    raw1 = _safe_llm_call(provider, system_prompt, user_prompt, config.judge_temperature, config.judge_max_output_tokens, json_mode=True)
    decision_data, judge_error = parse_judge_output_v2(raw1 or "")
    if decision_data is None:
        raw2 = _safe_llm_call(provider, system_prompt, user_prompt, config.judge_temperature, config.judge_max_output_tokens, json_mode=True)
        decision_data, judge_error = parse_judge_output_v2(raw2 or "")

    if decision_data is None:
        result = _run_smart_fallback(state, config)
        result["judge_error"] = judge_error or "Judge LLM 連續兩次呼叫失敗"
        result["judge_raw_response"] = _fmt_judge_raw(raw1, raw2)
        
        return result

    category = decision_data.get("category", "normal")
    fake_praise = _check_fake_praise(state)
    if fake_praise:
        category = "questioning"
        decision_data = {
            **decision_data,
            "category": "questioning",
            "event_type": "questioning",
            "validation_warnings": [
                *decision_data.get("validation_warnings", []),
                "fake_praise_reclassified",
            ],
        }

    result = {
        "category": category,
        "classifier_category": base_classification.get("category", "normal"),
        "trigger": base_classification.get("trigger", ""),
        "keyword_signals": base_classification.get("keyword_signals", []),
        "keyword_confidence": base_classification.get("keyword_confidence", "none"),
        "uncertain_flag": base_classification.get("uncertain_flag", False),
        "judge_source": "llm",
        "judge_raw_response": raw1 or "",
        "judge_error": "",
        "fake_praise": fake_praise,
        "ambiguous_flag": bool(decision_data.get("ambiguous_flag")) or bool(base_classification.get("ambiguous_flag")) or fake_praise,
        "sarcasm_possible": bool(decision_data.get("sarcasm_possible")),
        "requires_action": bool(decision_data.get("requires_action")),
        "intent_target": decision_data.get("intent_target", "unknown"),
        "event_analysis": decision_data,  # Store the full rich JSON from LLM
    }

    return result
