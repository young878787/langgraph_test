"""Transactional in-memory persistence for proactive initiative tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Callable, Optional, TypeVar

from .domain import (
    DecisionRecord,
    DeliveryAttempt,
    DomainValidationError,
    EventStatus,
    InitiativeEvent,
)


class StoreConflictError(RuntimeError):
    """Raised on optimistic-version or uniqueness conflicts."""


class InMemoryInitiativeStore:
    def __init__(self) -> None:
        self._events: dict[tuple[tuple[str, str, str, str], str, str], InitiativeEvent] = {}
        self._event_keys: dict[str, tuple[tuple[str, str, str, str], str, str]] = {}
        self._event_idempotency: set[tuple[tuple[str, str, str, str], str, str]] = set()
        self._decisions: list[DecisionRecord] = []
        self._deliveries: dict[tuple[tuple[str, str, str, str], str, str], DeliveryAttempt] = {}
        self._activation_tokens: set[str] = set()

    def unit_of_work(self) -> "InitiativeUnitOfWork":
        return InitiativeUnitOfWork(self)

    def _key(self, event: InitiativeEvent) -> tuple[tuple[str, str, str, str], str, str]:
        return event.identity.isolation_key, event.run_id, event.event_id

    def create_event(self, event: InitiativeEvent) -> InitiativeEvent:
        key = self._key(event)
        unique = event.identity.isolation_key, event.run_id, event.idempotency_key
        if event.event_id in self._event_keys or key in self._events:
            raise StoreConflictError("event_id already exists")
        if unique in self._event_idempotency:
            raise StoreConflictError("event idempotency_key already exists")
        self._events[key] = event
        self._event_keys[event.event_id] = key
        self._event_idempotency.add(unique)
        return event

    def get_event(self, event_id: str, *, isolation_key: tuple[str, str, str, str], run_id: str) -> InitiativeEvent:
        key = isolation_key, run_id, event_id
        try:
            return self._events[key]
        except KeyError as exc:
            raise KeyError("event not found in this isolation namespace") from exc

    def save_event(self, event: InitiativeEvent, *, expected_version: int) -> InitiativeEvent:
        key = self._key(event)
        current = self._events.get(key)
        if current is None:
            raise KeyError(event.event_id)
        if current.version != expected_version or event.version != expected_version + 1:
            raise StoreConflictError("optimistic version conflict")
        self._events[key] = event
        return event

    def append_decision(self, record: DecisionRecord) -> None:
        if any(item.decision_id == record.decision_id for item in self._decisions):
            raise StoreConflictError("decision_id already exists")
        self._decisions.append(record)

    def decisions_for(self, event_id: str) -> tuple[DecisionRecord, ...]:
        return tuple(item for item in self._decisions if item.event_id == event_id)

    def create_delivery(self, attempt: DeliveryAttempt, event: InitiativeEvent) -> None:
        key = event.identity.isolation_key, event.run_id, attempt.idempotency_key
        existing = self._deliveries.get(key)
        if existing is not None:
            if existing.content_hash != attempt.content_hash:
                raise StoreConflictError("idempotency key cannot be reused with different content")
            raise StoreConflictError("delivery idempotency_key already exists")
        self._deliveries[key] = attempt

    def activate_draft(self, event_id: str, *, isolation_key: tuple[str, str, str, str], run_id: str, activation_token: str, source_turn_id: str) -> InitiativeEvent:
        event = self.get_event(event_id, isolation_key=isolation_key, run_id=run_id)
        if event.status is not EventStatus.DRAFT:
            raise StoreConflictError("event is not a DRAFT")
        if activation_token != event.activation_token or activation_token in self._activation_tokens:
            raise StoreConflictError("activation token is invalid or already used")
        if source_turn_id not in event.source_turn_ids:
            raise DomainValidationError("activation must bind a persisted source turn")
        activated = replace(event, status=EventStatus.SCHEDULED, version=event.version + 1, activation_token=None)
        self.save_event(activated, expected_version=event.version)
        self._activation_tokens.add(activation_token)
        return activated


class InitiativeUnitOfWork:
    """Rollback-on-error boundary for event, decision and delivery writes."""

    def __init__(self, store: InMemoryInitiativeStore) -> None:
        self.store = store
        self._snapshot: Optional[dict[str, object]] = None

    def __enter__(self) -> "InitiativeUnitOfWork":
        self._snapshot = deepcopy(self.store.__dict__)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        if exc_type is not None and self._snapshot is not None:
            self.store.__dict__.clear()
            self.store.__dict__.update(self._snapshot)
        return False


T = TypeVar("T")


def event_first_commitment(
    store: InMemoryInitiativeStore,
    event: InitiativeEvent,
    generate_expression: Callable[[], T],
    persist_transcript: Callable[[T], str],
) -> tuple[InitiativeEvent, T]:
    """Create DRAFT, persist its expression, then consume activation exactly once."""

    with store.unit_of_work():
        store.create_event(event)
        expression = generate_expression()
        source_turn_id = persist_transcript(expression)
        activated = store.activate_draft(
            event.event_id,
            isolation_key=event.identity.isolation_key,
            run_id=event.run_id,
            activation_token=event.activation_token or "",
            source_turn_id=source_turn_id,
        )
    return activated, expression

