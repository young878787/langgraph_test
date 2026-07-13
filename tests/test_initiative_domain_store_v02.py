from __future__ import annotations

import sys
import types
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
if "agent" not in sys.modules:
    package = types.ModuleType("agent")
    package.__path__ = [str(ROOT / "src" / "agent")]
    sys.modules["agent"] = package

from agent.initiative.domain import (  # noqa: E402
    DecisionRecord,
    DeliveryAttempt,
    DomainValidationError,
    EventSchedule,
    EventStatus,
    InitiativeAction,
    InitiativeEvent,
    InitiativePlan,
    IsolationIdentity,
    UnsupportedActionError,
    apply_action,
    complete_delivery,
)
from agent.initiative.store import (  # noqa: E402
    InMemoryInitiativeStore,
    StoreConflictError,
    event_first_commitment,
)

TZ = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 13, 10, 0, tzinfo=TZ)


def make_event(event_id: str = "evt-1", key: str = "world:turn:continuation") -> InitiativeEvent:
    identity = IsolationIdentity("tenant", "user", "character", "world", "session", "test", "channel", "test:user")
    return InitiativeEvent(
        event_id=event_id, run_id="run", identity=identity, initiative_level="L0",
        source_turn_ids=("turn-1",), summary="稍後回來",
        schedule=EventSchedule(NOW + timedelta(minutes=5), NOW + timedelta(minutes=30), NOW + timedelta(minutes=5)),
        idempotency_key=key, activation_token="activation-1",
    )


class DomainSeparationTests(unittest.TestCase):
    def test_event_plan_decision_and_delivery_have_distinct_responsibilities(self) -> None:
        event = make_event()
        plan = InitiativePlan("plan", event.event_id, 1, "eval", "continue", True, ("turn:turn-1",), InitiativeAction.SEND_NOW, NOW)
        decision = DecisionRecord("decision", event.event_id, 1, plan.plan_id, InitiativeAction.SEND_NOW, ("promise_due",), NOW)
        delivery = DeliveryAttempt("delivery", event.event_id, decision.decision_id, "evt:send:1", event.identity.delivery_target, "sha256:a", NOW)
        self.assertFalse(hasattr(plan, "status"))
        self.assertFalse(hasattr(event, "decision_candidate"))
        self.assertEqual(delivery.decision_id, decision.decision_id)

    def test_only_six_actions_are_enabled_and_terminal_events_cannot_wake(self) -> None:
        with self.assertRaises(UnsupportedActionError) as caught:
            apply_action(make_event(), "MERGE_WITH_OTHER_EVENT")
        self.assertEqual(str(caught.exception), "unsupported_action_for_version")
        cancelled = apply_action(make_event(), InitiativeAction.CANCEL)
        self.assertEqual(cancelled.status, EventStatus.CANCELLED)
        self.assertIsNone(cancelled.schedule.next_evaluation_at)
        with self.assertRaises(DomainValidationError):
            apply_action(cancelled, InitiativeAction.SEND_NOW)

    def test_delay_presence_and_delivery_rules_are_deterministic(self) -> None:
        event = make_event()
        with self.assertRaises(DomainValidationError):
            apply_action(event, InitiativeAction.DELAY)
        delayed = apply_action(event, InitiativeAction.DELAY, next_evaluation_at=NOW + timedelta(minutes=10))
        self.assertEqual(delayed.status, EventStatus.DELAYED)
        waiting = apply_action(event, InitiativeAction.WAIT_FOR_USER_ACTIVITY, presence_subscription_key="presence", expiry_wakeup_at=event.schedule.expires_at)
        self.assertEqual(waiting.status, EventStatus.WAITING_FOR_PRESENCE)
        self.assertEqual(waiting.expiry_wakeup_at, event.schedule.expires_at)
        pending = apply_action(event, InitiativeAction.SEND_NOW)
        self.assertEqual(complete_delivery(pending).status, EventStatus.COMPLETED)


class StoreAndCommitmentTests(unittest.TestCase):
    def test_store_enforces_isolation_idempotency_and_optimistic_version(self) -> None:
        store = InMemoryInitiativeStore()
        event = make_event()
        store.create_event(event)
        with self.assertRaises(StoreConflictError):
            store.create_event(make_event("evt-2"))
        changed = replace(event, summary="changed", version=2)
        store.save_event(changed, expected_version=1)
        with self.assertRaises(StoreConflictError):
            store.save_event(replace(changed, version=3), expected_version=1)
        with self.assertRaises(KeyError):
            store.get_event(event.event_id, isolation_key=("tenant", "other", "character", "world"), run_id="run")

    def test_decisions_are_append_only_and_delivery_key_is_unique(self) -> None:
        store = InMemoryInitiativeStore()
        event = make_event()
        store.create_event(event)
        decision = DecisionRecord("decision", event.event_id, 1, "plan", InitiativeAction.SEND_NOW, ("due",), NOW)
        store.append_decision(decision)
        with self.assertRaises(StoreConflictError):
            store.append_decision(decision)
        delivery = DeliveryAttempt("delivery", event.event_id, decision.decision_id, "send-key", "test:user", "sha256:a", NOW)
        store.create_delivery(delivery, event)
        with self.assertRaises(StoreConflictError):
            store.create_delivery(replace(delivery, delivery_id="other", content_hash="sha256:b"), event)

    def test_event_first_gate_rolls_back_and_activation_token_is_single_use(self) -> None:
        store = InMemoryInitiativeStore()
        event = make_event()
        activated, expression = event_first_commitment(store, event, lambda: "五分鐘後回來", lambda _: "turn-1")
        self.assertEqual((expression, activated.status), ("五分鐘後回來", EventStatus.SCHEDULED))
        with self.assertRaises(StoreConflictError):
            store.activate_draft(event.event_id, isolation_key=event.identity.isolation_key, run_id=event.run_id, activation_token="activation-1", source_turn_id="turn-1")

        failed_store = InMemoryInitiativeStore()
        with self.assertRaises(RuntimeError):
            event_first_commitment(failed_store, event, lambda: "承諾", lambda _: (_ for _ in ()).throw(RuntimeError("transcript failed")))
        with self.assertRaises(KeyError):
            failed_store.get_event(event.event_id, isolation_key=event.identity.isolation_key, run_id=event.run_id)


if __name__ == "__main__":
    unittest.main()
