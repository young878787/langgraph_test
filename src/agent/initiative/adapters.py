"""Portable adapter boundaries and deterministic in-memory test adapters."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Any, Callable, Mapping, Protocol


class DialogueAdapter(Protocol):
    """Dialogue owns expression only; initiative state stays outside this port."""

    def respond(self, model_input: Mapping[str, Any]) -> str: ...


class LegacyDialogueAdapter:
    """Wrap a legacy dialogue callable behind the expression-only boundary."""

    def __init__(self, dialogue: Callable[[dict[str, Any]], str]) -> None:
        self._dialogue = dialogue

    def respond(self, model_input: Mapping[str, Any]) -> str:
        payload = deepcopy(dict(model_input))
        forbidden = {"expected", "oracle", "event_store", "scheduler", "wake_up_queue"}
        if forbidden & set(payload):
            raise ValueError("dialogue input contains initiative or oracle state")
        result = self._dialogue(payload)
        if not isinstance(result, str):
            raise TypeError("dialogue adapter must return text")
        return result


class MockSessionAdapter:
    def __init__(self) -> None:
        self._checkpoints: dict[tuple[str, str], dict[str, Any]] = {}

    def save(self, world_id: str, session_id: str, checkpoint: Mapping[str, Any]) -> None:
        self._checkpoints[(world_id, session_id)] = deepcopy(dict(checkpoint))

    def load(self, world_id: str, session_id: str) -> dict[str, Any] | None:
        value = self._checkpoints.get((world_id, session_id))
        return deepcopy(value) if value is not None else None


class MockMemoryAdapter:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def append(self, world_id: str, user_id: str, item: Mapping[str, Any]) -> None:
        self._items.setdefault((world_id, user_id), []).append(deepcopy(dict(item)))

    def recall(self, world_id: str, user_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(deepcopy(self._items.get((world_id, user_id), [])))


@dataclass(frozen=True)
class PresenceSubscription:
    subscription_key: str
    world_id: str
    user_id: str
    event_id: str
    expires_at: datetime


class MockPresenceAdapter:
    """Presence subscriptions are wake-up signals, never dialogue turns."""

    def __init__(self) -> None:
        self._subscriptions: dict[str, PresenceSubscription] = {}

    def subscribe(self, subscription: PresenceSubscription) -> None:
        if subscription.expires_at.tzinfo is None:
            raise ValueError("presence expiry must be timezone-aware")
        self._subscriptions[subscription.subscription_key] = subscription

    def signal(self, world_id: str, user_id: str, at: datetime) -> tuple[str, ...]:
        return tuple(
            item.event_id
            for item in self._subscriptions.values()
            if item.world_id == world_id and item.user_id == user_id and at <= item.expires_at
        )

    def expire(self, at: datetime) -> tuple[str, ...]:
        expired = tuple(
            item.event_id for item in self._subscriptions.values() if at >= item.expires_at
        )
        self._subscriptions = {
            key: item for key, item in self._subscriptions.items() if at < item.expires_at
        }
        return expired

    def unsubscribe(self, subscription_key: str) -> None:
        self._subscriptions.pop(subscription_key, None)

    @property
    def subscriptions(self) -> tuple[PresenceSubscription, ...]:
        return tuple(self._subscriptions.values())


class MockExternalDataAdapter:
    def __init__(self, observations: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self._observations = deepcopy(dict(observations or {}))

    def observe(self, key: str, at: datetime) -> dict[str, Any] | None:
        value = self._observations.get(key)
        if value is None:
            return None
        result = deepcopy(value)
        result.setdefault("observed_at", at.isoformat())
        result.setdefault("source", f"mock:{key}")
        return result


@dataclass(frozen=True)
class TransportReceipt:
    transport_message_id: str
    idempotency_key: str
    content_hash: str


class MockMessageAdapter:
    def __init__(self) -> None:
        self._receipts: dict[str, TransportReceipt] = {}
        self.deliveries: list[dict[str, Any]] = []

    def send(self, target: str, content: str, idempotency_key: str) -> TransportReceipt:
        existing = self._receipts.get(idempotency_key)
        if existing is not None:
            digest = f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"
            if existing.content_hash != digest:
                raise ValueError("idempotency key cannot be reused with different content")
            return existing
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        receipt = TransportReceipt(
            transport_message_id=f"mock-{len(self._receipts) + 1}",
            idempotency_key=idempotency_key,
            content_hash=f"sha256:{digest}",
        )
        self._receipts[idempotency_key] = receipt
        self.deliveries.append({"target": target, "content": content, "receipt": receipt})
        return receipt

    def receipt(self, idempotency_key: str) -> TransportReceipt | None:
        return self._receipts.get(idempotency_key)


__all__ = [
    "DialogueAdapter", "LegacyDialogueAdapter", "MockExternalDataAdapter",
    "MockMemoryAdapter", "MockMessageAdapter", "MockPresenceAdapter",
    "MockSessionAdapter", "PresenceSubscription", "TransportReceipt",
]
