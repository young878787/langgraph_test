"""Strict JSON contracts for live initiative decisions.

These parsers accept exactly one JSON object.  They intentionally reject
Markdown fences, unknown fields, implicit coercion, and absolute model-owned
timestamps so provider output cannot silently widen the runtime contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import json
from typing import Any, Iterable, Mapping

from .contracts import require_timezone_aware
from .domain import InitiativeAction


class DecisionContractError(ValueError):
    """Raised when a live decision does not satisfy its exact contract."""

    def __init__(self, errors: Iterable[str]) -> None:
        self.errors = tuple(dict.fromkeys(str(item) for item in errors if str(item)))
        super().__init__("; ".join(self.errors) or "invalid decision contract")


class WorldEventType(str, Enum):
    REMINDER = "reminder"
    CARE_FOLLOWUP = "care_followup"
    COMMITMENT = "commitment"
    TOPIC_CONTINUATION = "topic_continuation"


class InterruptionRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TriggerKind(str, Enum):
    TIME = "time"
    PRESENCE = "presence"
    USER_ACTIVITY = "user_activity"
    WORLD_SIGNAL = "world_signal"


@dataclass(frozen=True)
class ProposalTrigger:
    kind: TriggerKind
    earliest_offset_minutes: int
    preferred_offset_minutes: int
    expires_offset_minutes: int


@dataclass(frozen=True)
class WorldEventCandidate:
    candidate_id: str
    event_type: WorldEventType
    summary: str
    evidence_refs: tuple[str, ...]
    followup_value: str
    interruption_risk: InterruptionRisk
    trigger: ProposalTrigger
    confidence: float
    short_rationale: str


@dataclass(frozen=True)
class CandidateScanDecision:
    schema_version: str
    decision_type: str
    events: tuple[WorldEventCandidate, ...]
    no_event_reason: str | None


@dataclass(frozen=True)
class MergedCandidate:
    target_candidate_id: str
    source_candidate_ids: tuple[str, ...]


@dataclass(frozen=True)
class RejectedCandidate:
    candidate_id: str
    reason_code: str


@dataclass(frozen=True)
class CandidateConsolidationDecision:
    schema_version: str
    decision_type: str
    accepted_candidate_ids: tuple[str, ...]
    merged_candidates: tuple[MergedCandidate, ...]
    rejected_candidates: tuple[RejectedCandidate, ...]
    short_rationale: str


@dataclass(frozen=True)
class WakeUpReappraisalDecision:
    schema_version: str
    decision_type: str
    event_id: str
    event_version: int
    action: InitiativeAction
    reason_code: str
    evidence_refs: tuple[str, ...]
    next_evaluation_offset_minutes: int | None
    next_evaluation_at: datetime | None
    short_rationale: str


_SCAN_KEYS = {"schema_version", "decision_type", "events", "no_event_reason"}
_EVENT_KEYS = {
    "candidate_id", "event_type", "summary", "evidence_refs", "followup_value",
    "interruption_risk", "trigger", "confidence", "short_rationale",
}
_TRIGGER_KEYS = {
    "kind", "earliest_offset_minutes", "preferred_offset_minutes",
    "expires_offset_minutes",
}
_CONSOLIDATION_KEYS = {
    "schema_version", "decision_type", "accepted_candidate_ids",
    "merged_candidates", "rejected_candidates", "short_rationale",
}
_MERGED_KEYS = {"target_candidate_id", "source_candidate_ids"}
_REJECTED_KEYS = {"candidate_id", "reason_code"}
_REAPPRAISAL_KEYS = {
    "schema_version", "decision_type", "event_id", "event_version", "action",
    "reason_code", "evidence_refs", "next_evaluation_offset_minutes",
    "short_rationale",
}


def _json_object(raw: str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if not isinstance(raw, str) or not raw.strip():
        raise DecisionContractError(("output must be a non-empty JSON object",))
    text = raw.strip()
    if text.startswith("```"):
        raise DecisionContractError(("Markdown code fences are not allowed",))
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DecisionContractError((f"invalid JSON: {exc.msg}",)) from exc
    if not isinstance(value, dict):
        raise DecisionContractError(("JSON root must be an object",))
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    errors = []
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        errors.append(f"{label} missing fields: {', '.join(missing)}")
    if unknown:
        errors.append(f"{label} unknown fields: {', '.join(unknown)}")
    if errors:
        raise DecisionContractError(errors)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DecisionContractError((f"{field} must be a non-empty string",))
    return value.strip()


def _string_array(value: Any, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise DecisionContractError((f"{field} must be an array of non-empty strings",))
    normalized = tuple(item.strip() for item in value)
    if not allow_empty and not normalized:
        raise DecisionContractError((f"{field} must not be empty",))
    if len(normalized) != len(set(normalized)):
        raise DecisionContractError((f"{field} must not contain duplicates",))
    return normalized


def _integer(value: Any, field: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DecisionContractError((f"{field} must be an integer",))
    if minimum is not None and value < minimum:
        raise DecisionContractError((f"{field} must be >= {minimum}",))
    return value


def _enum(enum_type: type[Enum], value: Any, field: str) -> Any:
    if not isinstance(value, str):
        raise DecisionContractError((f"{field} must be a string enum",))
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise DecisionContractError((f"{field} must be one of: {allowed}",)) from exc


def parse_candidate_scan(
    raw: str | Mapping[str, Any],
    *,
    available_evidence_refs: Iterable[str],
    max_events: int = 3,
    max_horizon_minutes: int = 7 * 24 * 60,
) -> CandidateScanDecision:
    data = _json_object(raw)
    _exact_keys(data, _SCAN_KEYS, "candidate_scan")
    if data["schema_version"] != "initiative.world_event_proposal.v1":
        raise DecisionContractError(("unsupported candidate_scan schema_version",))
    if data["decision_type"] != "candidate_scan":
        raise DecisionContractError(("decision_type must be candidate_scan",))
    if isinstance(max_events, bool) or not isinstance(max_events, int) or max_events < 0:
        raise ValueError("max_events must be a non-negative integer")
    events_raw = data["events"]
    if not isinstance(events_raw, list):
        raise DecisionContractError(("events must be an array",))
    if len(events_raw) > max_events:
        raise DecisionContractError((f"events exceeds maximum of {max_events}",))
    available = set(available_evidence_refs)
    events: list[WorldEventCandidate] = []
    for index, item in enumerate(events_raw):
        label = f"events[{index}]"
        if not isinstance(item, Mapping):
            raise DecisionContractError((f"{label} must be an object",))
        _exact_keys(item, _EVENT_KEYS, label)
        trigger = item["trigger"]
        if not isinstance(trigger, Mapping):
            raise DecisionContractError((f"{label}.trigger must be an object",))
        _exact_keys(trigger, _TRIGGER_KEYS, f"{label}.trigger")
        earliest = _integer(trigger["earliest_offset_minutes"], f"{label}.trigger.earliest_offset_minutes", minimum=0)
        preferred = _integer(trigger["preferred_offset_minutes"], f"{label}.trigger.preferred_offset_minutes", minimum=0)
        expires = _integer(trigger["expires_offset_minutes"], f"{label}.trigger.expires_offset_minutes", minimum=0)
        if not earliest <= preferred < expires:
            raise DecisionContractError((f"{label}.trigger offsets must satisfy earliest <= preferred < expires",))
        if expires > max_horizon_minutes:
            raise DecisionContractError((f"{label}.trigger exceeds configured horizon",))
        refs = _string_array(item["evidence_refs"], f"{label}.evidence_refs", allow_empty=False)
        unknown_refs = sorted(set(refs) - available)
        if unknown_refs:
            raise DecisionContractError((f"{label}.evidence_refs are unknown: {', '.join(unknown_refs)}",))
        confidence = item["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise DecisionContractError((f"{label}.confidence must be a number",))
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            raise DecisionContractError((f"{label}.confidence must be between 0 and 1",))
        events.append(WorldEventCandidate(
            candidate_id=_text(item["candidate_id"], f"{label}.candidate_id"),
            event_type=_enum(WorldEventType, item["event_type"], f"{label}.event_type"),
            summary=_text(item["summary"], f"{label}.summary"),
            evidence_refs=refs,
            followup_value=_text(item["followup_value"], f"{label}.followup_value"),
            interruption_risk=_enum(InterruptionRisk, item["interruption_risk"], f"{label}.interruption_risk"),
            trigger=ProposalTrigger(
                _enum(TriggerKind, trigger["kind"], f"{label}.trigger.kind"),
                earliest, preferred, expires,
            ),
            confidence=confidence,
            short_rationale=_text(item["short_rationale"], f"{label}.short_rationale"),
        ))
    ids = [item.candidate_id for item in events]
    if len(ids) != len(set(ids)):
        raise DecisionContractError(("candidate_id values must be unique",))
    no_event_reason = data["no_event_reason"]
    if events and no_event_reason is not None:
        raise DecisionContractError(("no_event_reason must be null when events are present",))
    if not events:
        no_event_reason = _text(no_event_reason, "no_event_reason")
    return CandidateScanDecision(data["schema_version"], data["decision_type"], tuple(events), no_event_reason)


def parse_candidate_consolidation(
    raw: str | Mapping[str, Any], *, known_candidate_ids: Iterable[str]
) -> CandidateConsolidationDecision:
    data = _json_object(raw)
    _exact_keys(data, _CONSOLIDATION_KEYS, "candidate_consolidation")
    if data["schema_version"] != "initiative.world_event_consolidation.v1":
        raise DecisionContractError(("unsupported candidate_consolidation schema_version",))
    if data["decision_type"] != "candidate_consolidation":
        raise DecisionContractError(("decision_type must be candidate_consolidation",))
    known = set(known_candidate_ids)
    accepted = _string_array(data["accepted_candidate_ids"], "accepted_candidate_ids")
    merged_raw = data["merged_candidates"]
    rejected_raw = data["rejected_candidates"]
    if not isinstance(merged_raw, list) or not isinstance(rejected_raw, list):
        raise DecisionContractError(("merged_candidates and rejected_candidates must be arrays",))
    merged: list[MergedCandidate] = []
    merged_sources: list[str] = []
    for index, item in enumerate(merged_raw):
        if not isinstance(item, Mapping):
            raise DecisionContractError((f"merged_candidates[{index}] must be an object",))
        _exact_keys(item, _MERGED_KEYS, f"merged_candidates[{index}]")
        target = _text(item["target_candidate_id"], f"merged_candidates[{index}].target_candidate_id")
        sources = _string_array(item["source_candidate_ids"], f"merged_candidates[{index}].source_candidate_ids", allow_empty=False)
        if target in sources:
            raise DecisionContractError(("merged candidate cannot target itself",))
        merged.append(MergedCandidate(target, sources))
        merged_sources.extend(sources)
    rejected: list[RejectedCandidate] = []
    for index, item in enumerate(rejected_raw):
        if not isinstance(item, Mapping):
            raise DecisionContractError((f"rejected_candidates[{index}] must be an object",))
        _exact_keys(item, _REJECTED_KEYS, f"rejected_candidates[{index}]")
        rejected.append(RejectedCandidate(
            _text(item["candidate_id"], f"rejected_candidates[{index}].candidate_id"),
            _text(item["reason_code"], f"rejected_candidates[{index}].reason_code"),
        ))
    rejected_ids = [item.candidate_id for item in rejected]
    referenced = set(accepted) | set(merged_sources) | set(rejected_ids) | {item.target_candidate_id for item in merged}
    unknown = sorted(referenced - known)
    if unknown:
        raise DecisionContractError((f"consolidation references unknown candidates: {', '.join(unknown)}",))
    if any(item.target_candidate_id not in accepted for item in merged):
        raise DecisionContractError(("merged candidate target must be accepted",))
    dispositions = list(accepted) + merged_sources + rejected_ids
    if len(dispositions) != len(set(dispositions)):
        raise DecisionContractError(("candidate dispositions must be mutually exclusive",))
    omitted = sorted(known - set(dispositions))
    if omitted:
        raise DecisionContractError((f"consolidation omitted candidates: {', '.join(omitted)}",))
    return CandidateConsolidationDecision(
        data["schema_version"], data["decision_type"], accepted, tuple(merged),
        tuple(rejected), _text(data["short_rationale"], "short_rationale"),
    )


def parse_wake_up_reappraisal(
    raw: str | Mapping[str, Any],
    *,
    expected_event_id: str,
    expected_event_version: int,
    available_evidence_refs: Iterable[str],
    logical_now: datetime,
    expires_at: datetime,
) -> WakeUpReappraisalDecision:
    require_timezone_aware(logical_now, field="logical_now")
    require_timezone_aware(expires_at, field="expires_at")
    data = _json_object(raw)
    _exact_keys(data, _REAPPRAISAL_KEYS, "wake_up_reappraisal")
    if data["schema_version"] != "initiative.reappraisal.v1":
        raise DecisionContractError(("unsupported reappraisal schema_version",))
    if data["decision_type"] != "wake_up_reappraisal":
        raise DecisionContractError(("decision_type must be wake_up_reappraisal",))
    event_id = _text(data["event_id"], "event_id")
    if event_id != expected_event_id:
        raise DecisionContractError(("event_id does not match current event",))
    event_version = _integer(data["event_version"], "event_version", minimum=1)
    if event_version != expected_event_version:
        raise DecisionContractError(("event_version does not match current event",))
    action = _enum(InitiativeAction, data["action"], "action")
    refs = _string_array(data["evidence_refs"], "evidence_refs")
    unknown = sorted(set(refs) - set(available_evidence_refs))
    if unknown:
        raise DecisionContractError((f"evidence_refs are unknown: {', '.join(unknown)}",))
    offset = data["next_evaluation_offset_minutes"]
    next_at = None
    if action is InitiativeAction.DELAY:
        offset = _integer(offset, "next_evaluation_offset_minutes", minimum=1)
        next_at = logical_now + timedelta(minutes=offset)
        if next_at > expires_at:
            raise DecisionContractError(("next evaluation exceeds event expiry",))
    elif offset is not None:
        raise DecisionContractError(("next_evaluation_offset_minutes must be null unless action is DELAY",))
    return WakeUpReappraisalDecision(
        data["schema_version"], data["decision_type"], event_id, event_version,
        action, _text(data["reason_code"], "reason_code"), refs, offset, next_at,
        _text(data["short_rationale"], "short_rationale"),
    )


__all__ = [
    "CandidateConsolidationDecision", "CandidateScanDecision", "DecisionContractError",
    "InterruptionRisk", "MergedCandidate", "ProposalTrigger", "RejectedCandidate",
    "TriggerKind", "WakeUpReappraisalDecision", "WorldEventCandidate", "WorldEventType",
    "parse_candidate_consolidation", "parse_candidate_scan", "parse_wake_up_reappraisal",
]
