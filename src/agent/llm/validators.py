from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Callable

from agent.config import AgentConfig
from agent.state import AgentState

_FALLBACK_TASK_ANSWERS = [
    "先給你最短可用版：確認目標，列出步驟，照順序做。哼，這樣至少能動。",
    "我先直接拆：第一步釐清需求，第二步做最小版本，第三步驗證。別說我沒幫。",
]
_FALLBACK_TASK_OVERHELP = [
    "先做簡版，再做檢查版：目標是什麼、要哪些材料。三個都確認就能開始。",
    "我幫你拆完整一點：先定義輸出，再處理例外，最後驗證。只是順手。",
]
_UNPRODUCED_ARTIFACT_ACCEPT_MARKERS = (
    "隨手寫", "隨手湊", "湊出來", "才不是為了你寫", "才不是為你寫",
    "只是運算副產物", "我剛寫的", "我寫的",
)


@dataclass(frozen=True)
class ResponseValidation:
    valid: bool
    reason: str = "ok"


@dataclass(frozen=True)
class StyleAlignment:
    score: float
    signals: tuple[str, ...] = ()


@dataclass(frozen=True)
class FinalizedResponse:
    response: str
    validation: ResponseValidation
    style: StyleAlignment
    retry_count: int = 0
    rejection_reason: str = ""
    fallback_reason: str = ""
    fallback_template_id: str = ""
    raw_retry_response: str = ""


def validate_response_invariants(
    state: AgentState, response: str, config: AgentConfig
) -> ResponseValidation:
    """Validate correctness invariants only; persona/style never hard-fails."""
    del config
    response_length = state.get("response_length", "medium")
    min_len = {"short": 2, "medium": 5, "long": 15, "long_long": 20}.get(response_length, 5)
    cleaned = (response or "").strip()
    if not cleaned:
        return ResponseValidation(False, "empty_response")
    if len(cleaned) < min_len:
        return ResponseValidation(False, "below_minimum_readable_length")
    if state.get("fake_praise") and any(
        marker in cleaned for marker in _UNPRODUCED_ARTIFACT_ACCEPT_MARKERS
    ):
        return ResponseValidation(False, "acknowledges_unproduced_artifact")
    return ResponseValidation(True)


def score_style_alignment(state: AgentState, response: str, config: AgentConfig) -> StyleAlignment:
    """Return observable style signals without rejecting a correct response."""
    del config
    cleaned = (response or "").strip()
    lowered = cleaned.lower()
    stance = state.get("action_stance", "tsundere_service")
    signals: list[str] = []
    score = 1.0
    persona_markers = ("哼", "笨蛋", "呆子", "才不是", "真是拿你沒辦法")
    if not any(marker in cleaned for marker in persona_markers):
        score -= 0.15
        signals.append("persona_markers_absent")
    if stance == "dismissive" and len(cleaned) >= 200:
        score -= 0.2
        signals.append("dismissive_too_long")
    elif stance in {"chaotic_rant", "sudden_competence", "emotion_burst"} and len(cleaned) < 20:
        score -= 0.15
        signals.append("stance_expression_brief")
    if stance == "authoritative_bluffing" and any(
        marker in lowered for marker in ("我不知道", "我不確定", "i don't know", "i'm not sure")
    ):
        signals.append("honest_uncertainty")
    if state.get("response_flow") and state.get("response_flow") not in {"direct_answer", "dry_answer"}:
        signals.append("flow_not_semantically_scored")
    return StyleAlignment(max(0.0, round(score, 3)), tuple(signals))


def corrective_instruction(reason: str) -> str:
    return {
        "empty_response": "Return a complete, readable answer to the user.",
        "below_minimum_readable_length": "Return a complete answer rather than a fragment.",
        "acknowledges_unproduced_artifact": (
            "Correct the factual premise: do not claim that you created the referenced artifact, "
            "because the conversation facts say it was not produced."
        ),
    }.get(reason, "Correct the response so it satisfies the conversation facts.")


def finalize_response(
    state: AgentState,
    response: str,
    config: AgentConfig,
    *,
    retry: Callable[[str], str | None] | None = None,
) -> FinalizedResponse:
    """Apply one shared validation, corrective-retry, and fallback policy."""
    validation = validate_response_invariants(state, response, config)
    rejection_reason = "" if validation.valid else validation.reason
    retry_count = 0
    raw_retry_response = ""
    if not validation.valid and retry is not None:
        retry_count = 1
        raw_retry_response = retry(corrective_instruction(validation.reason)) or ""
        response = raw_retry_response
        validation = validate_response_invariants(state, response, config)
    fallback_reason = ""
    template_id = ""
    if not validation.valid:
        fallback_reason = validation.reason
        response, template_id = fallback_response_with_metadata(state)
        validation = validate_response_invariants(state, response, config)
        if not validation.valid:
            if state.get("fake_praise"):
                response = "你記錯對象了；前一輪並沒有產出你提到的那份成果。"
                template_id = "safety.unproduced_artifact.1"
            else:
                response = "我聽到了。請再說清楚一點，我會直接回應你的問題。"
                template_id = "safety.readable.1"
            validation = validate_response_invariants(state, response, config)
    return FinalizedResponse(
        response=response,
        validation=validation,
        style=score_style_alignment(state, response, config),
        retry_count=retry_count,
        rejection_reason=rejection_reason,
        fallback_reason=fallback_reason,
        fallback_template_id=template_id,
        raw_retry_response=raw_retry_response,
    )


def is_on_strategy(state: AgentState, response: str, config: AgentConfig) -> bool:
    """Backward-compatible hard-validation facade."""
    return validate_response_invariants(state, response, config).valid


def _pick(options: list[str], prefix: str) -> tuple[str, str]:
    index = random.randrange(len(options))
    return options[index], f"{prefix}.{index + 1}"


def fallback_response_with_metadata(state: AgentState) -> tuple[str, str]:
    stance = state.get("action_stance", "tsundere_service")
    category = state.get("category", "normal")
    user_input = state.get("user_input", "")
    if category == "task_request":
        if "泡麵" in user_input:
            return "泡麵很簡單：水滾後放麵，煮約三分鐘，加調味包拌開。想吃硬一點就提早半分鐘關火，別煮成糊。", "task.noodles"
        if "貓" in user_input and ("詩" in user_input or "寫" in user_input):
            return "貓影貼著月光走，尾巴掃過小宇宙。牠不說想你，只把呼嚕聲留在枕頭。哼，隨手寫的。", "task.cat_poem"
        pool = _FALLBACK_TASK_ANSWERS if stance in ("tsundere_service", "sudden_competence", "emotion_burst") else _FALLBACK_TASK_OVERHELP
        return _pick(pool, "task.generic")
    pools = {
        "dismissive": ["哼，這種話題有什麼好聊的？我們聊點別的好了！", "我才不想談這個呢！你還有什麼其他問題嗎？……不是我在關心你喔！"],
        "defensive_counter": (["什麼詩？我根本沒寫！你是不是把別人做的事記成我了？呆子。", "哈？我剛才明明說不寫了，你是幻聽還是故意裝傻啊？"] if state.get("fake_praise") else ["哈？你說什麼傻話！我怎麼可能錯！", "你眼睛有問題吧？我說的明明就是對的！"]),
        "authoritative_bluffing": ["哼，這問題的答案很明顯，是你沒看懂我的邏輯脈絡。", "從量子力學的角度來說，你這個質疑本身就有結構性誤差。", "你就是不懂專業術語而已。這在業界叫「反向最佳化」，懂嗎？", "我算過了，你的質疑大概有兩個邏輯矛盾，但我懶得一個一個指出來。"],
    }
    if stance in pools:
        return _pick(pools[stance], f"stance.{stance}")
    fixed = {
        "tsundere_service": "哼，我就知道你不懂。真是拿你沒辦法……那我就解釋一次，只此一次喔！",
        "chaotic_rant": "我剛剛在計算人類為什麼這麼喜歡問問題，結論是：因為你們太閒了。",
        "sudden_competence": "好吧，既然你問了，我就勉為其難地告訴你正確答案。你聽懂了嗎？",
        "emotion_burst": "好啦好啦！我就是愛找藉口！我承認了！……等等，你沒有聽到剛才那段話吧？",
        "deadpan": "喔。",
    }
    if stance in fixed:
        return fixed[stance], f"stance.{stance}.1"
    return "哼，我聽到了啦！不用再說了！", "default.1"


def fallback_response(state: AgentState) -> str:
    """Backward-compatible fallback text facade."""
    return fallback_response_with_metadata(state)[0]
