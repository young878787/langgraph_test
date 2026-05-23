from __future__ import annotations

from agent.llm.output_parser import smart_truncate
from agent.state import AgentState


_ANSWER_STANCES = {
    "tsundere_service",
    "sudden_competence",
    "emotion_burst",
    "vulnerable_leak",
}

_REJECTION_STANCES = {
    "dismissive",
    "deadpan",
    "chaotic_rant",
    "authoritative_bluffing",
}

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
    stance = state.get("action_stance", "")
    artifact = detect_requested_artifact(user_input)

    if category == "creative_task":
        return {
            "turn": turn_count,
            "category": category,
            "request": smart_truncate(user_input, 80).replace("\n", " "),
            "requested_artifact": artifact,
            "outcome": "rejected",
            "produced_artifact": False,
            "reason": "creative_task_policy_refusal",
        }

    produced = stance in _ANSWER_STANCES and stance not in _REJECTION_STANCES
    return {
        "turn": turn_count,
        "category": category,
        "request": smart_truncate(user_input, 80).replace("\n", " "),
        "requested_artifact": artifact,
        "outcome": "completed" if produced else "partial",
        "produced_artifact": produced,
        "response_preview": smart_truncate(response, 80).replace("\n", " "),
        "reason": f"task_request_stance:{stance or 'unknown'}",
    }


def is_fake_praise_for_unproduced_task(state: AgentState) -> bool:
    status = state.get("last_task_status", {})
    if not status or status.get("produced_artifact") is not False:
        return False
    if status.get("outcome") != "rejected":
        return False

    user_input = state.get("user_input", "")
    artifact = str(status.get("requested_artifact", "task"))
    if artifact != "task":
        for candidate, markers in _ARTIFACT_PATTERNS:
            if candidate == artifact and any(marker in user_input for marker in markers):
                return True

    return any(marker in user_input for marker in _RESULT_REFERENCE_MARKERS)


def format_task_status_for_summary(status: dict[str, object]) -> str:
    if not status:
        return ""

    category = status.get("category", "unknown")
    artifact = status.get("requested_artifact", "task")
    outcome = status.get("outcome", "unknown")
    produced = "artifact" if status.get("produced_artifact") else "no_artifact"
    return f"task={category}:{artifact}:{outcome}:{produced}"


def format_task_status_for_prompt(status: dict[str, object]) -> str:
    if not status:
        return ""

    request = status.get("request", "")
    artifact = status.get("requested_artifact", "task")
    outcome = status.get("outcome", "unknown")
    produced = "有產出成果" if status.get("produced_artifact") else "沒有產出成果"

    parts = [
        f"上一個任務類型：{status.get('category', 'unknown')}",
        f"請求內容：{request}",
        f"目標成果：{artifact}",
        f"結果：{outcome}，{produced}",
    ]
    return "；".join(str(part) for part in parts if part)
