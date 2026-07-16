"""Deterministic persistence gate for accepted world-event proposals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
from typing import Iterable

from .contracts import require_timezone_aware
from .decision_contracts import (
    CandidateConsolidationDecision,
    CandidateScanDecision,
    InterruptionRisk,
    WorldEventCandidate,
    WorldEventType,
)
from .domain import EventSchedule, EventStatus, InitiativeEvent, IsolationIdentity, TERMINAL_STATUSES
from .store import InMemoryInitiativeStore


@dataclass(frozen=True)
class EventGatePolicy:
    max_events_per_conversation: int = 2
    max_active_events_per_world: int = 5
    max_horizon_minutes: int = 7 * 24 * 60
    max_chain_depth: int = 3

    def __post_init__(self) -> None:
        values = (
            self.max_events_per_conversation,
            self.max_active_events_per_world,
            self.max_horizon_minutes,
            self.max_chain_depth,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("event gate bounds must be non-negative integers")


@dataclass(frozen=True)
class EventGateContext:
    logical_now: datetime
    identity: IsolationIdentity
    run_id: str
    available_evidence_refs: tuple[str, ...]
    active_events: tuple[InitiativeEvent, ...] = ()
    opted_out_event_types: tuple[WorldEventType | str, ...] = ()
    sensitive_event_types: tuple[WorldEventType | str, ...] = ()
    sensitive_candidate_ids: tuple[str, ...] = ()
    chain_depth: int = 0

    def __post_init__(self) -> None:
        require_timezone_aware(self.logical_now, field="logical_now")
        object.__setattr__(self, "available_evidence_refs", tuple(self.available_evidence_refs))
        object.__setattr__(self, "active_events", tuple(self.active_events))
        object.__setattr__(self, "opted_out_event_types", tuple(self.opted_out_event_types))
        object.__setattr__(self, "sensitive_event_types", tuple(self.sensitive_event_types))
        object.__setattr__(self, "sensitive_candidate_ids", tuple(self.sensitive_candidate_ids))
        if not self.run_id:
            raise ValueError("run_id is required")
        if isinstance(self.chain_depth, bool) or not isinstance(self.chain_depth, int) or self.chain_depth < 0:
            raise ValueError("chain_depth must be a non-negative integer")


@dataclass(frozen=True)
class AcceptedEvent:
    candidate: WorldEventCandidate
    event: InitiativeEvent


@dataclass(frozen=True)
class RejectedEvent:
    candidate_id: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class EventGateResult:
    accepted: tuple[AcceptedEvent, ...]
    rejected: tuple[RejectedEvent, ...]


def _event_type_values(items: Iterable[WorldEventType | str]) -> set[str]:
    return {item.value if isinstance(item, WorldEventType) else str(item) for item in items}


def _event_id(run_id: str, candidate_id: str) -> str:
    digest = hashlib.sha256(f"{run_id}\n{candidate_id}".encode("utf-8")).hexdigest()[:20]
    return f"event:{digest}"


def _level(event_type: WorldEventType) -> str:
    if event_type is WorldEventType.REMINDER:
        return "L1"
    if event_type is WorldEventType.COMMITMENT:
        return "L0"
    return "L2"


def _build_event(candidate: WorldEventCandidate, context: EventGateContext) -> InitiativeEvent:
    earliest_at = context.logical_now + timedelta(minutes=candidate.trigger.earliest_offset_minutes)
    preferred_at = context.logical_now + timedelta(minutes=candidate.trigger.preferred_offset_minutes)
    expires_at = context.logical_now + timedelta(minutes=candidate.trigger.expires_offset_minutes)
    event_id = _event_id(context.run_id, candidate.candidate_id)
    return InitiativeEvent(
        event_id=event_id,
        run_id=context.run_id,
        identity=context.identity,
        initiative_level=_level(candidate.event_type),
        source_turn_ids=candidate.evidence_refs,
        summary=candidate.summary,
        schedule=EventSchedule(earliest_at, expires_at, preferred_at),
        status=EventStatus.DRAFT,
        idempotency_key=f"{context.run_id}:{candidate.candidate_id}:create",
        activation_token=f"{context.run_id}:{candidate.candidate_id}:activate",
    )


def gate_candidate_events(
    scan: CandidateScanDecision,
    consolidation: CandidateConsolidationDecision,
    context: EventGateContext,
    *,
    policy: EventGatePolicy = EventGatePolicy(),
) -> EventGateResult:
    """Validate accepted candidates and build DRAFT events without persisting them."""

    by_id = {item.candidate_id: item for item in scan.events}
    opted_out = _event_type_values(context.opted_out_event_types)
    sensitive_types = _event_type_values(context.sensitive_event_types)
    sensitive_ids = set(context.sensitive_candidate_ids)
    evidence = set(context.available_evidence_refs)
    active = tuple(
        event for event in context.active_events
        if event.identity.isolation_key == context.identity.isolation_key
        and event.status not in TERMINAL_STATUSES
    )
    accepted: list[AcceptedEvent] = []
    rejected: list[RejectedEvent] = []
    accepted_ids = set(consolidation.accepted_candidate_ids)

    for candidate in scan.events:
        reasons: list[str] = []
        if candidate.candidate_id not in accepted_ids:
            reasons.append("not_accepted_by_consolidation")
        if not set(candidate.evidence_refs) <= evidence:
            reasons.append("unknown_evidence_ref")
        if candidate.trigger.expires_offset_minutes > policy.max_horizon_minutes:
            reasons.append("horizon_exceeded")
        if candidate.event_type.value in opted_out:
            reasons.append("user_opt_out")
        if context.chain_depth >= policy.max_chain_depth:
            reasons.append("chain_depth_exceeded")
        if candidate.candidate_id in sensitive_ids or candidate.event_type.value in sensitive_types:
            reasons.append("sensitive_inference_rejected")
        if candidate.interruption_risk is InterruptionRisk.HIGH:
            reasons.append("high_interruption_risk")
        if any(
            event.summary.strip().casefold() == candidate.summary.strip().casefold()
            for event in (*active, *(item.event for item in accepted))
        ):
            reasons.append("duplicate_active_event")
        if len(active) + len(accepted) >= policy.max_active_events_per_world:
            reasons.append("active_event_limit")
        if len(accepted) >= policy.max_events_per_conversation:
            reasons.append("conversation_event_limit")
        if reasons:
            rejected.append(RejectedEvent(candidate.candidate_id, tuple(dict.fromkeys(reasons))))
            continue
        accepted.append(AcceptedEvent(candidate, _build_event(candidate, context)))

    unknown_accepted = sorted(accepted_ids - set(by_id))
    rejected.extend(RejectedEvent(item, ("unknown_candidate_id",)) for item in unknown_accepted)
    return EventGateResult(tuple(accepted), tuple(rejected))


def persist_accepted_events(
    result: EventGateResult,
    store: InMemoryInitiativeStore,
) -> tuple[InitiativeEvent, ...]:
    """Persist and activate only events previously accepted by the gate."""

    persisted: list[InitiativeEvent] = []
    for accepted in result.accepted:
        event = accepted.event
        source_turn_id = event.source_turn_ids[0]
        with store.unit_of_work():
            store.create_event(event)
            activated = store.activate_draft(
                event.event_id,
                isolation_key=event.identity.isolation_key,
                run_id=event.run_id,
                activation_token=event.activation_token or "",
                source_turn_id=source_turn_id,
            )
        persisted.append(activated)
    return tuple(persisted)


__all__ = [
    "AcceptedEvent", "EventGateContext", "EventGatePolicy", "EventGateResult",
    "RejectedEvent", "gate_candidate_events", "persist_accepted_events",
]
