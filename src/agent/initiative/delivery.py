"""Deterministic exactly-once delivery adapter and recovery store."""
from __future__ import annotations
import asyncio, hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

def content_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode()).hexdigest()

@dataclass(frozen=True)
class TransportReceipt:
    idempotency_key: str
    transport_message_id: str
    content_hash: str

class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"

@dataclass(frozen=True)
class DeliveryAttempt:
    event_id: str; event_version: int; idempotency_key: str; target: str; content: str
    content_hash: str; attempted_at: datetime
    status: DeliveryStatus = DeliveryStatus.PENDING
    transport_message_id: str | None = None

class ContentConflictError(ValueError): pass

class MockMessageAdapter:
    def __init__(self) -> None:
        self.receipts: dict[str, TransportReceipt] = {}; self.messages: list[tuple[str,str,str]] = []
        self.timeout_after_send = False
    async def send(self, *, idempotency_key: str, target: str, content: str) -> TransportReceipt:
        digest = content_hash(content); existing = self.receipts.get(idempotency_key)
        if existing:
            if existing.content_hash != digest: raise ContentConflictError("key reused with different content")
            return existing
        receipt = TransportReceipt(idempotency_key, f"mock_message_{len(self.messages)+1}", digest)
        self.receipts[idempotency_key] = receipt
        self.messages.append((target, content, receipt.transport_message_id))
        if self.timeout_after_send: raise TimeoutError("simulated timeout after send")
        return receipt
    async def get_receipt(self, key: str) -> TransportReceipt | None: return self.receipts.get(key)

class DeliveryStore:
    def __init__(self) -> None:
        self.attempts: dict[str, DeliveryAttempt] = {}; self._event_versions: dict[str,int] = {}
        self._lock = asyncio.Lock()
    async def claim(self, attempt: DeliveryAttempt) -> tuple[DeliveryAttempt,bool]:
        async with self._lock:
            existing = self.attempts.get(attempt.idempotency_key)
            if existing:
                if existing.content_hash != attempt.content_hash: raise ContentConflictError("retry hash differs")
                return existing, False
            current = self._event_versions.get(attempt.event_id, attempt.event_version)
            if current != attempt.event_version: raise RuntimeError("stale event version")
            self._event_versions[attempt.event_id] = current + 1
            self.attempts[attempt.idempotency_key] = attempt
            return attempt, True
    async def mark_delivered(self, key: str, receipt: TransportReceipt) -> DeliveryAttempt:
        async with self._lock:
            attempt = self.attempts[key]
            if attempt.content_hash != receipt.content_hash: raise ContentConflictError("receipt hash mismatch")
            result = replace(attempt, status=DeliveryStatus.DELIVERED,
                             transport_message_id=receipt.transport_message_id)
            self.attempts[key] = result; return result

class ExactlyOnceDelivery:
    def __init__(self, store: DeliveryStore, transport: MockMessageAdapter) -> None:
        self.store, self.transport = store, transport
    async def deliver(self, attempt: DeliveryAttempt, *, crash_after_send: bool=False) -> DeliveryAttempt:
        claimed, _ = await self.store.claim(attempt)
        if claimed.status is DeliveryStatus.DELIVERED: return claimed
        receipt = await self.transport.get_receipt(claimed.idempotency_key)
        if receipt is None:
            try: receipt = await self.transport.send(idempotency_key=claimed.idempotency_key,
                                                     target=claimed.target, content=claimed.content)
            except TimeoutError:
                receipt = await self.transport.get_receipt(claimed.idempotency_key)
                if receipt is None: raise
        if crash_after_send: raise RuntimeError("simulated crash after send")
        return await self.store.mark_delivered(claimed.idempotency_key, receipt)
