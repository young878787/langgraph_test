"""Event-driven, bounded runtime adapters for proactive wake-ups."""
from __future__ import annotations
import asyncio
import heapq
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum
from typing import Awaitable, Callable
from .clock import Clock
from .contracts import require_timezone_aware

class WakeKind(IntEnum):
    USER_MESSAGE = 1
    CANCELLATION = 2
    EXPIRY = 3
    PRESENCE = 4
    DUE_EVALUATION = 5
    DELIVERY_RETRY = 6
    WORLD_UPDATE = 7

_LEVEL_PRIORITY = {"L1": 0, "L0": 1, "L2": 2}

@dataclass(frozen=True)
class WakeItem:
    scheduled_at: datetime
    kind: WakeKind
    event_id: str
    run_id: str
    world_id: str
    initiative_level: str = "L2"
    created_at: datetime | None = None
    payload: object = None
    def __post_init__(self) -> None:
        require_timezone_aware(self.scheduled_at, field="scheduled_at")
        if self.created_at is not None:
            require_timezone_aware(self.created_at, field="created_at")
    @property
    def sort_key(self) -> tuple[object, ...]:
        return (self.scheduled_at, int(self.kind), _LEVEL_PRIORITY.get(self.initiative_level, 99),
                self.created_at or self.scheduled_at, self.event_id)

class WakeQueueClosed(RuntimeError): pass

class WakeUpQueue:
    """Heap queue woken only by insertion, clock advance, or shutdown."""
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self._heap: list[tuple[tuple[object, ...], WakeItem]] = []
        self._changed = asyncio.Event()
        self._closed = False
        subscribe = getattr(clock, "subscribe", None)
        self._unsubscribe = subscribe(lambda _: self._changed.set()) if subscribe else None
    def put_nowait(self, item: WakeItem) -> None:
        if self._closed:
            raise WakeQueueClosed("wake-up queue no longer accepts events")
        heapq.heappush(self._heap, (item.sort_key, item))
        self._changed.set()
    async def put(self, item: WakeItem) -> None:
        self.put_nowait(item)
    async def get_due(self) -> WakeItem | None:
        while True:
            if self._heap and self._heap[0][1].scheduled_at <= self.clock.now():
                return heapq.heappop(self._heap)[1]
            if self._closed:
                return None
            self._changed.clear()
            await self._changed.wait()
    def close(self) -> None:
        self._closed = True
        if self._unsubscribe:
            self._unsubscribe(); self._unsubscribe = None
        self._changed.set()
    @property
    def empty(self) -> bool: return not self._heap

@dataclass
class LeaseRegistry:
    clock: Clock
    _leases: dict[tuple[str, str, str], tuple[str, datetime]] = field(default_factory=dict)
    def acquire(self, item: WakeItem, owner: str, ttl: timedelta) -> bool:
        key = (item.run_id, item.world_id, item.event_id)
        held = self._leases.get(key)
        if held and held[1] > self.clock.now() and held[0] != owner: return False
        self._leases[key] = (owner, self.clock.now() + ttl); return True
    def release(self, item: WakeItem, owner: str) -> None:
        key = (item.run_id, item.world_id, item.event_id)
        if self._leases.get(key, (None,))[0] == owner: self._leases.pop(key, None)
    def release_owner(self, owner: str) -> None:
        for key, lease in tuple(self._leases.items()):
            if lease[0] == owner: self._leases.pop(key, None)

class RuntimeLimitExceeded(RuntimeError): pass

class BoundedWorker:
    def __init__(self, *, worker_id: str, queue: WakeUpQueue,
                 handler: Callable[[WakeItem], Awaitable[None]], leases: LeaseRegistry,
                 max_steps: int = 100, max_events: int = 100,
                 lease_ttl: timedelta = timedelta(minutes=1)) -> None:
        if max_steps <= 0 or max_events <= 0: raise ValueError("worker limits must be positive")
        self.worker_id, self.queue, self.handler, self.leases = worker_id, queue, handler, leases
        self.max_steps, self.max_events, self.lease_ttl = max_steps, max_events, lease_ttl
        self.steps = self.events = 0
        self._task: asyncio.Task[None] | None = None
    def start(self) -> asyncio.Task[None]:
        if self._task and not self._task.done(): return self._task
        self._task = asyncio.create_task(self.run(), name=f"initiative-worker:{self.worker_id}")
        return self._task
    async def run(self) -> None:
        try:
            while True:
                item = await self.queue.get_due()
                if item is None: return
                self.steps += 1
                if self.steps > self.max_steps: raise RuntimeLimitExceeded("maximum worker steps exceeded")
                if not self.leases.acquire(item, self.worker_id, self.lease_ttl): continue
                try:
                    self.events += 1
                    if self.events > self.max_events: raise RuntimeLimitExceeded("maximum processed events exceeded")
                    await self.handler(item)
                finally: self.leases.release(item, self.worker_id)
        finally: self.leases.release_owner(self.worker_id)
    async def shutdown(self, *, graceful: bool = True) -> None:
        self.queue.close()
        if not self._task: return
        if not graceful and not self._task.done(): self._task.cancel()
        try: await self._task
        except asyncio.CancelledError: pass
