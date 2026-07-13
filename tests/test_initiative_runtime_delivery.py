from datetime import datetime, timezone
import asyncio
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
if "agent" not in sys.modules:
    package = types.ModuleType("agent")
    package.__path__ = [str(ROOT / "src" / "agent")]
    sys.modules["agent"] = package

from agent.initiative.clock import FakeClock
from agent.initiative.delivery import DeliveryAttempt, DeliveryStatus, DeliveryStore, ExactlyOnceDelivery, MockMessageAdapter, content_hash
from agent.initiative.runtime import BoundedWorker, LeaseRegistry, WakeItem, WakeKind, WakeUpQueue

NOW = datetime(2026, 7, 13, 10, tzinfo=timezone.utc)

async def _append(target, item): target.append(item.event_id)

def _attempt(content="hello"):
    return DeliveryAttempt("evt", 1, "evt:send:1", "console:user", content, content_hash(content), NOW)

class RuntimeDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_clock_advance_wakes_worker_and_stable_precedence(self):
        clock = FakeClock(NOW); queue = WakeUpQueue(clock); seen = []
        worker = BoundedWorker(worker_id="w1", queue=queue, handler=lambda item: _append(seen,item), leases=LeaseRegistry(clock))
        worker.start()
        due = clock.advance(minutes=5)
        for kind in (WakeKind.DUE_EVALUATION, WakeKind.PRESENCE, WakeKind.EXPIRY):
            queue.put_nowait(WakeItem(due, kind, kind.name, "run", "world", "L2", NOW))
        await asyncio.sleep(0); await asyncio.sleep(0)
        await worker.shutdown()
        self.assertEqual(seen, ["EXPIRY", "PRESENCE", "DUE_EVALUATION"])
        self.assertTrue(worker._task.done())

    async def test_duplicate_wake_and_two_workers_share_one_lease(self):
        clock = FakeClock(NOW); queue = WakeUpQueue(clock); leases = LeaseRegistry(clock)
        gate = asyncio.Event(); seen = []
        async def handle(item): seen.append(item.event_id); await gate.wait()
        item = WakeItem(NOW, WakeKind.DUE_EVALUATION, "evt", "run", "world")
        queue.put_nowait(item); queue.put_nowait(item)
        workers = [BoundedWorker(worker_id=f"w{i}", queue=queue, handler=handle, leases=leases) for i in range(2)]
        for worker in workers: worker.start()
        await asyncio.sleep(0); gate.set(); await asyncio.sleep(0)
        for worker in workers: await worker.shutdown()
        self.assertEqual(seen, ["evt"])

    async def test_crash_after_send_recovers_from_receipt_without_duplicate(self):
        store, transport = DeliveryStore(), MockMessageAdapter(); delivery = ExactlyOnceDelivery(store, transport)
        with self.assertRaisesRegex(RuntimeError, "crash after send"):
            await delivery.deliver(_attempt(), crash_after_send=True)
        result = await delivery.deliver(_attempt())
        self.assertIs(result.status, DeliveryStatus.DELIVERED)
        self.assertEqual(len(transport.messages), 1)

    async def test_timeout_and_competing_workers_reuse_identity_and_content(self):
        store, transport = DeliveryStore(), MockMessageAdapter(); transport.timeout_after_send = True
        delivery = ExactlyOnceDelivery(store, transport)
        first, second = await asyncio.gather(delivery.deliver(_attempt()), delivery.deliver(_attempt()))
        self.assertEqual(first.transport_message_id, second.transport_message_id)
        self.assertEqual(len(transport.messages), 1)
