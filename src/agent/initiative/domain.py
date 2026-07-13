"""Versioned proactive initiative domain objects and state transitions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Optional

from .contracts import InitiativeContractError, require_timezone_aware


SCHEMA_VERSION = 1


class DomainValidationError(InitiativeContractError):
    """Raised when a v0.2 domain invariant is violated."""


class UnsupportedActionError(DomainValidationError):
    """Raised for actions outside the first research version."""


class InitiativeAction(str, Enum):
    SEND_NOW = "SEND_NOW"
    DELAY = "DELAY"
    WAIT_FOR_USER_ACTIVITY = "WAIT_FOR_USER_ACTIVITY"
    CANCEL = "CANCEL"
    EXPIRE = "EXPIRE"
    SILENCE = "SILENCE"


class EventStatus(str, Enum):
    DRAFT = "DRAFT"
    CREATED = "CREATED"
    SCHEDULED = "SCHEDULED"
    DUE = "DUE"
    EVALUATING = "EVALUATING"
    DELAYED = "DELAYED"
    WAITING_FOR_PRESENCE = "WAITING_FOR_PRESENCE"
    DELIVERY_PENDING = "DELIVERY_PENDING"
    DELIVERED = "DELIVERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    SILENCED = "SILENCED"


TERMINAL_STATUSES = frozenset(
    {EventStatus.EXPIRED, EventStatus.CANCELLED, EventStatus.SILENCED, EventStatus.COMPLETED}
)


@dataclass(frozen=True)
class IsolationIdentity:
    tenant_id: str
    user_id: str
    character_id: str
    world_id: str
    source_session_id: str
    source_platform: str
    source_channel_id: str
    delivery_target: str

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if not isinstance(value, str) or not value.strip():
                raise DomainValidationError(f"identity.{name} is required")

    @property
    def isolation_key(self) -> tuple[str, str, str, str]:
        return self.tenant_id, self.user_id, self.character_id, self.world_id


@dataclass(frozen=True)
class EventSchedule:
    earliest_at: datetime
    expires_at: datetime
    next_evaluation_at: Optional[datetime]

    def __post_init__(self) -> None:
        require_timezone_aware(self.earliest_at, field="earliest_at")
        require_timezone_aware(self.expires_at, field="expires_at")
        if self.next_evaluation_at is not None:
            require_timezone_aware(self.next_evaluation_at, field="next_evaluation_at")
        if self.earliest_at > self.expires_at:
            raise DomainValidationError("earliest_at must not exceed expires_at")
        if self.next_evaluation_at is not None and not (
            self.earliest_at <= self.next_evaluation_at <= self.expires_at
        ):
            raise DomainValidationError("next_evaluation_at must be inside the event window")


@dataclass(frozen=True)
class InitiativeEvent:
    event_id: str
    run_id: str
    identity: IsolationIdentity
    initiative_level: str
    source_turn_ids: tuple[str, ...]
    summary: str
    schedule: EventSchedule
    status: EventStatus = EventStatus.DRAFT
    version: int = 1
    schema_version: int = SCHEMA_VERSION
    idempotency_key: str = ""
    activation_token: Optional[str] = None
    presence_subscription_key: Optional[str] = None
    expiry_wakeup_at: Optional[datetime] = None
    requires_acknowledgement: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_turn_ids", tuple(self.source_turn_ids))
        if self.schema_version != SCHEMA_VERSION:
            raise DomainValidationError(f"unsupported schema_version: {self.schema_version}")
        if not self.event_id or not self.run_id or not self.idempotency_key:
            raise DomainValidationError("event_id, run_id and idempotency_key are required")
        if self.initiative_level not in {"L0", "L1", "L2"}:
            raise DomainValidationError("initiative_level must be L0, L1 or L2")
        if not self.source_turn_ids:
            raise DomainValidationError("source_turn_ids are required")
        if self.version < 1:
            raise DomainValidationError("version must be positive")
        if self.status is EventStatus.DRAFT and not self.activation_token:
            raise DomainValidationError("DRAFT events require an activation_token")
        if self.status in TERMINAL_STATUSES and (
            self.schedule.next_evaluation_at is not None or self.presence_subscription_key
        ):
            raise DomainValidationError("terminal events cannot retain wake-ups")


@dataclass(frozen=True)
class InitiativePlan:
    plan_id: str
    event_id: str
    event_version: int
    evaluation_id: str
    goal: str
    should_initiate: bool
    evidence_refs: tuple[str, ...]
    decision_candidate: InitiativeAction
    created_at: datetime
    next_evaluation_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        require_timezone_aware(self.created_at, field="created_at")
        if self.next_evaluation_at is not None:
            require_timezone_aware(self.next_evaluation_at, field="next_evaluation_at")


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    event_id: str
    event_version_before: int
    plan_id: str
    action: InitiativeAction
    reason_codes: tuple[str, ...]
    decided_at: datetime
    next_evaluation_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        require_timezone_aware(self.decided_at, field="decided_at")
        if not self.reason_codes:
            raise DomainValidationError("reason_codes are required")


@dataclass(frozen=True)
class DeliveryAttempt:
    delivery_id: str
    event_id: str
    decision_id: str
    idempotency_key: str
    target: str
    content_hash: str
    attempted_at: datetime
    status: str = "PENDING"
    transport_message_id: Optional[str] = None

    def __post_init__(self) -> None:
        require_timezone_aware(self.attempted_at, field="attempted_at")
        if not all((self.delivery_id, self.event_id, self.decision_id, self.idempotency_key)):
            raise DomainValidationError("delivery identity fields are required")


def parse_action(value: InitiativeAction | str) -> InitiativeAction:
    try:
        return value if isinstance(value, InitiativeAction) else InitiativeAction(value)
    except (TypeError, ValueError) as exc:
        raise UnsupportedActionError("unsupported_action_for_version") from exc


def apply_action(
    event: InitiativeEvent,
    action: InitiativeAction | str,
    *,
    next_evaluation_at: Optional[datetime] = None,
    presence_subscription_key: Optional[str] = None,
    expiry_wakeup_at: Optional[datetime] = None,
) -> InitiativeEvent:
    """Validate one of the six enabled actions and return the next event version."""

    selected = parse_action(action)
    if event.status in TERMINAL_STATUSES:
        raise DomainValidationError("terminal events cannot transition")
    schedule = event.schedule
    updates: dict[str, object] = {
        "version": event.version + 1,
        "presence_subscription_key": None,
        "expiry_wakeup_at": None,
    }
    if selected is InitiativeAction.SEND_NOW:
        updates.update(status=EventStatus.DELIVERY_PENDING, schedule=replace(schedule, next_evaluation_at=None))
    elif selected is InitiativeAction.DELAY:
        if next_evaluation_at is None:
            raise DomainValidationError("DELAY requires next_evaluation_at")
        require_timezone_aware(next_evaluation_at, field="next_evaluation_at")
        if not (schedule.earliest_at <= next_evaluation_at <= schedule.expires_at):
            raise DomainValidationError("next_evaluation_at must be inside the event window")
        updates.update(status=EventStatus.DELAYED, schedule=replace(schedule, next_evaluation_at=next_evaluation_at))
    elif selected is InitiativeAction.WAIT_FOR_USER_ACTIVITY:
        if not presence_subscription_key or expiry_wakeup_at is None:
            raise DomainValidationError(
                "WAIT_FOR_USER_ACTIVITY requires presence subscription and expiry wake-up"
            )
        require_timezone_aware(expiry_wakeup_at, field="expiry_wakeup_at")
        if expiry_wakeup_at != schedule.expires_at:
            raise DomainValidationError("expiry wake-up must equal expires_at")
        updates.update(
            status=EventStatus.WAITING_FOR_PRESENCE,
            schedule=replace(schedule, next_evaluation_at=None),
            presence_subscription_key=presence_subscription_key,
            expiry_wakeup_at=expiry_wakeup_at,
        )
    else:
        status = {
            InitiativeAction.CANCEL: EventStatus.CANCELLED,
            InitiativeAction.EXPIRE: EventStatus.EXPIRED,
            InitiativeAction.SILENCE: EventStatus.SILENCED,
        }[selected]
        updates.update(status=status, schedule=replace(schedule, next_evaluation_at=None))
    return replace(event, **updates)


def complete_delivery(event: InitiativeEvent) -> InitiativeEvent:
    if event.status is not EventStatus.DELIVERY_PENDING:
        raise DomainValidationError("only DELIVERY_PENDING can complete delivery")
    terminal = event.initiative_level in {"L0", "L2"} or not event.requires_acknowledgement
    return replace(
        event,
        status=EventStatus.COMPLETED if terminal else EventStatus.DELIVERED,
        version=event.version + 1,
    )

