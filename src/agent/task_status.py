from __future__ import annotations

from agent.llm.output_parser import smart_truncate
from agent.state import AgentState


_ARTIFACT_PATTERNS = (
    ("poem", ("詩", "寫一首", "寫首詩", "作一首", "一首詩")),
    ("translation", ("翻譯", "翻成", "日文", "英文")),
    ("story", ("故事", "小說")),
    ("code", ("程式", "代碼", "code", "script")),
    ("image", ("畫", "圖片", "圖像")),
    ("copy", ("文案", "文章", "標題")),
)

_RESULT_REFERENCE_MARKERS = (
    "這首",
    "那首",
    "寫得",
    "翻得",
    "做得",
    "成果",
    "作品",
    "剛才那個",
    "剛剛那個",
)

_ARTIFACT_REFERENCE_PATTERNS = {
    "poem": ("你剛寫的詩", "你寫的那首詩", "剛才那首詩", "剛剛那首詩"),
    "translation": ("你剛翻的", "你翻譯的那段", "剛才的翻譯", "剛剛的翻譯"),
    "story": ("你剛寫的故事", "你寫的那個故事", "剛才的故事", "剛剛的故事"),
    "code": ("你剛寫的程式", "你寫的那段程式", "你剛寫的 code", "剛才那段 code"),
    "image": ("你剛畫的", "你畫的那張", "剛才那張圖", "剛剛那張圖"),
    "copy": ("你剛寫的文案", "你寫的那篇文章", "剛才的文案", "剛剛的文案"),
}

_TASK_STATUS_CONTEXT_CATEGORIES = {
    "questioning",
    "praise",
    "flirt",
}


def detect_requested_artifact(text: str) -> str:
    lowered = text.lower()
    for artifact, markers in _ARTIFACT_PATTERNS:
        if any(marker in lowered for marker in markers):
            return artifact
    return "task"


def build_task_status(state: AgentState, turn_count: int) -> dict[str, object]:
    category = state.get("category", "normal")
    if category not in ("creative_task", "task_request"):
        return dict(state.get("last_task_status", {}))

    user_input = state.get("user_input", "")
    response = state.get("response", "")
    artifact = detect_requested_artifact(user_input)

    observation = state.get("artifact_observation", {})
    observed_produced = observation.get("produced_artifact") if isinstance(observation, dict) else None
    if observed_produced not in (True, False):
        observed_produced = "unknown"
    observed_source = (
        str(observation.get("evidence_source", "response_observation"))
        if isinstance(observation, dict)
        else "response_observation"
    )

    if observed_produced in (True, False):
        outcome = "completed" if observed_produced else "rejected"
        evidence_source = observed_source
        reason = "artifact_observation"
    elif category == "creative_task":
        observed_produced = False
        outcome = "rejected"
        evidence_source = "policy:creative_task_boundary"
        reason = "creative_task_policy_refusal"
    elif state.get("fallback_used"):
        observed_produced = False
        outcome = "rejected"
        evidence_source = "response_fallback"
        reason = "deterministic_fallback_no_artifact"
    else:
        outcome = "unknown"
        evidence_source = "unobserved"
        reason = "artifact_not_observed"

    return {
        "turn": turn_count,
        "response_turn": turn_count,
        "category": category,
        "request_kind": category,
        "request": smart_truncate(user_input, 80).replace("\n", " "),
        "requested_artifact": artifact,
        "outcome": outcome,
        "produced_artifact": observed_produced,
        "evidence_source": evidence_source,
        "response_preview": smart_truncate(response, 80).replace("\n", " "),
        "reason": reason,
    }


def is_fake_praise_for_unproduced_task(state: AgentState) -> bool:
    status = state.get("last_task_status", {})
    if not status or status.get("produced_artifact") is not False:
        return False
    user_input = state.get("user_input", "")
    artifact = str(status.get("requested_artifact", "task"))
    references = _ARTIFACT_REFERENCE_PATTERNS.get(artifact, ())
    if references and any(marker in user_input for marker in references):
        return True

    return artifact == "task" and any(
        marker in user_input
        for marker in ("你剛做的成果", "你剛完成的成果", "你剛才做的那個", "你剛剛做的那個")
    )


def format_task_status_for_summary(status: dict[str, object]) -> str:
    if not status:
        return ""

    category = status.get("category", "unknown")
    artifact = status.get("requested_artifact", "task")
    outcome = status.get("outcome", "unknown")
    produced_value = status.get("produced_artifact")
    produced = "artifact" if produced_value is True else "no_artifact" if produced_value is False else "unknown_artifact"
    source = status.get("evidence_source", "unknown")
    return f"task={category}:{artifact}:{outcome}:{produced}:source={source}"


def format_task_status_for_prompt(status: dict[str, object]) -> str:
    if not status:
        return ""

    request = status.get("request", "")
    artifact = status.get("requested_artifact", "task")
    outcome = status.get("outcome", "unknown")
    produced_value = status.get("produced_artifact")
    produced = "有產出成果" if produced_value is True else "沒有產出成果" if produced_value is False else "是否產出未知"
    evidence_source = status.get("evidence_source", "unknown")

    parts = [
        f"上一個任務類型：{status.get('category', 'unknown')}",
        f"請求內容：{request}",
        f"目標成果：{artifact}",
        f"結果：{outcome}，{produced}",
        f"事實來源：{evidence_source}",
    ]
    return "；".join(str(part) for part in parts if part)


def should_include_task_status_for_response(state: AgentState) -> bool:
    status = state.get("last_task_status", {})
    if not status:
        return False

    if state.get("fake_praise"):
        return True

    user_input = state.get("user_input", "")
    if any(marker in user_input for marker in _RESULT_REFERENCE_MARKERS):
        return True

    category = state.get("category", "normal")
    outcome = status.get("outcome", "")

    if outcome in ("partial", "rejected") and category in _TASK_STATUS_CONTEXT_CATEGORIES:
        return True

    return False
