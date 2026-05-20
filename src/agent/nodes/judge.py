from __future__ import annotations

import random

from agent.config import AgentConfig
from agent.state import AgentState
from agent.llm.judging import build_judge_prompts
from agent.llm.judge_validators import parse_judge_output, parse_judge_output_v2
from agent.llm.providers import get_provider
from agent.nodes.classifier import classify_input
from agent.nodes.defect import decide_defect_strategy
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
    """檢查 praise 分類是否為虛假稱讚（讚美 AI 未執行的任務）

    優先使用結構化任務狀態；若舊狀態尚未寫入，才退回最近一輪
    對話關鍵字檢查。
    """
    if is_fake_praise_for_unproduced_task(state):
        return True

    conv_hist = state.get("conversation_history", [])
    if len(conv_hist) < 2:
        return False

    refuse_markers = ("靈感", "沒心情", "不想", "不做", "不幫", "沒有", "拒絕", "不寫", "不畫")
    request_markers = ("幫我", "寫", "翻譯", "畫", "做", "教", "給", "告訴")

    # 取最近一組 (user, assistant)
    last_ai = conv_hist[-1]
    if last_ai.get("role") != "assistant":
        return False
    if len(conv_hist) < 2:
        return False
    prev_user = conv_hist[-2]
    if prev_user.get("role") != "user":
        return False

    ai_msg = last_ai.get("content", "")
    user_msg = prev_user.get("content", "")
    return any(m in user_msg for m in request_markers) and any(m in ai_msg for m in refuse_markers)


def _run_smart_fallback(state: AgentState, config: AgentConfig) -> AgentState:
    classification = classify_input(state, config)
    merged_state: AgentState = {**state, **classification}
    strategy = decide_defect_strategy(merged_state, config)
    category = classification.get("category", "normal")
    chosen_strategy = strategy.get("strategy", "normal")

    # 虛假稱讚偵測：praise/flirt 分類的事後驗證
    # 注意：flirt 也可能夾帶虛假稱讚（如「詩寫得好棒！你其實很厲害嘛」）
    fake_praise = _check_fake_praise(state)
    if fake_praise:
        category = "questioning"
        chosen_strategy = "deny"
        strategy["strategy"] = chosen_strategy

    emotion = state.get("emotion", 0.0)
    traits = state.get("traits", config.traits)
    if category == "creative_task":
        if emotion >= 0.5:
            chosen_strategy = random.choice(["deflect", "excuse"])
        elif traits.get("tsundere", 0.0) >= 0.6:
            chosen_strategy = "deflect"
        elif traits.get("excuse_prone", 0.0) >= 0.5:
            chosen_strategy = "excuse"
        else:
            chosen_strategy = "avoid"
        strategy["strategy"] = chosen_strategy
    elif category in ("flirt", "praise"):
        if emotion >= 0.55 and random.random() < 0.45:
            chosen_strategy = "emotion_burst"
        elif traits.get("perfectionist", 0.0) >= 0.25 and random.random() < 0.25:
            chosen_strategy = "sudden_competence"
        elif traits.get("tsundere", 0.0) >= 0.7 and random.random() < 0.55:
            chosen_strategy = "tsundere_retort"
        else:
            chosen_strategy = "normal"
        strategy["strategy"] = chosen_strategy

    if emotion < -0.3 and chosen_strategy in ("over_associate", "nonsense"):
        chosen_strategy = "tsundere_retort" if state.get("traits", {}).get("tsundere", 0.0) >= 0.7 else "normal"
        strategy["strategy"] = chosen_strategy

    return {
        **classification,
        "category": category,
        **strategy,
        "judge_source": "rule",
        "classifier_category": classification.get("category", "normal"),
        "judge_raw_response": "",
        "judge_error": "",
        "fake_praise": fake_praise,
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

    # 虛假稱讚偵測：LLM judge 結果的事後驗證（強制規則覆蓋）
    # 注意：flirt 也可能夾帶虛假稱讚（如「詩寫得好棒！你其實很厲害嘛」）
    fake_praise = _check_fake_praise(state)
    if fake_praise:
        category = "questioning"
        strategy = "deny"

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
        "fake_praise": fake_praise,
    }
