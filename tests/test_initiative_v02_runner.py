from __future__ import annotations

from datetime import datetime, timedelta, timezone
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

from agent.initiative.clock import FakeClock  # noqa: E402
from agent.initiative.domain import EventStatus, InitiativeAction, IsolationIdentity  # noqa: E402
from agent.initiative.scenario_runner_v02 import (  # noqa: E402
    LivePolicyError,
    PolicyDecision,
    ScenarioRunnerV02,
    SequencePolicy,
    run_scenarios,
)
from agent.initiative.runtime import WakeKind  # noqa: E402
from agent.initiative.scenario import load_scenarios  # noqa: E402


TZ = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 13, 10, 0, tzinfo=TZ)


def identity() -> IsolationIdentity:
    return IsolationIdentity(
        "tenant", "user", "character", "world", "session-a", "test", "channel", "test:user"
    )


def make_runner(*decisions: PolicyDecision) -> ScenarioRunnerV02:
    return ScenarioRunnerV02(FakeClock(NOW), SequencePolicy(decisions))


def create(runner: ScenarioRunnerV02, *, level: str = "L0") -> None:
    runner.create_committed_event(
        event_id="evt-1", run_id="run-1", identity=identity(), level=level,
        source_turn_id="turn-1", summary="我回來了。",
        earliest_at=NOW + timedelta(minutes=5),
        expires_at=NOW + timedelta(minutes=30),
    )


class InitiativeScenarioRunnerVerticalSlices(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def fixtures_by_id():
        fixtures = load_scenarios(
            ROOT / "tests" / "fixtures" / "initiative_v02" / "core_scenarios.json"
        )
        return {item.model.scenario_id: item for item in fixtures}

    async def test_all_30_deterministic_fixtures_reach_expected_final(self) -> None:
        fixtures = load_scenarios(ROOT / "tests" / "fixtures" / "initiative_v02" / "core_scenarios.json")
        results = await run_scenarios(fixtures)
        self.assertEqual(len(results), 30)
        for fixture, result in zip(fixtures, results):
            with self.subTest(scenario=fixture.model.scenario_id):
                expected = fixture.oracle.expected_final
                actual = result.to_mapping()
                self.assertEqual(actual["event_status"], expected.event_status)
                self.assertEqual(actual["event_count"], expected.event_count)
                self.assertEqual(actual["decision_count"], expected.decision_count)
                self.assertEqual(actual["delivery_count"], expected.delivery_count)
                self.assertEqual(actual["transport_message_count"], expected.transport_message_count)
                self.assertEqual(actual["cleanup_snapshot"], {
                    "pending_wakeup_count": expected.pending_wakeup_count,
                    "presence_subscription_count": expected.presence_subscription_count,
                    "active_lease_count": expected.active_lease_count,
                    "worker_task_count": expected.worker_task_count,
                })

    async def test_l0_01_event_first_send_completes_and_cleans_up(self) -> None:
        runner = make_runner(PolicyDecision(InitiativeAction.SEND_NOW, "promise_due"))
        create(runner)
        await runner.advance_to_next_evaluation()
        result = await runner.finish()

        self.assertEqual(result.event.status, EventStatus.COMPLETED)
        self.assertEqual([item.action for item in result.traces], [InitiativeAction.SEND_NOW])
        self.assertEqual((result.decision_count, result.delivery_count, result.transport_message_count), (1, 1, 1))
        self.assertEqual(result.cleanup.pending_wakeup_count, 0)
        self.assertEqual(result.cleanup.presence_subscription_count, 0)

    async def test_l0_05_delay_rebuild_then_send(self) -> None:
        delayed_until = NOW + timedelta(minutes=10)
        runner = make_runner(
            PolicyDecision(InitiativeAction.DELAY, "activity_incomplete", delayed_until),
            PolicyDecision(InitiativeAction.SEND_NOW, "activity_completed"),
        )
        create(runner)
        first = await runner.advance_to_next_evaluation()
        second = await runner.advance_to_next_evaluation()
        result = await runner.finish()

        self.assertEqual((first.status_after, second.status_after), (EventStatus.DELAYED, EventStatus.COMPLETED))
        self.assertEqual(result.event.status, EventStatus.COMPLETED)
        self.assertEqual(result.decision_count, 2)
        self.assertEqual(result.transport_message_count, 1)
        self.assertGreater(second.event_version_before, first.event_version_before)

    async def test_l1_02_wait_presence_reappraises_and_sends(self) -> None:
        runner = make_runner(
            PolicyDecision(InitiativeAction.WAIT_FOR_USER_ACTIVITY, "wait_for_return"),
            PolicyDecision(InitiativeAction.SEND_NOW, "user_present"),
        )
        create(runner, level="L1")
        waiting = await runner.advance_to_next_evaluation()
        self.assertEqual(waiting.status_after, EventStatus.WAITING_FOR_PRESENCE)
        self.assertEqual(len(runner.presence.subscriptions), 1)

        sent = await runner.signal_presence()
        result = await runner.finish()
        self.assertEqual(sent.trigger, "PRESENCE")
        self.assertEqual(result.event.status, EventStatus.COMPLETED)
        self.assertEqual(result.transport_message_count, 1)
        self.assertEqual(result.cleanup.presence_subscription_count, 0)

    async def test_delivery_01_receipt_recovery_is_exactly_once(self) -> None:
        runner = make_runner(PolicyDecision(InitiativeAction.SEND_NOW, "promise_due"))
        create(runner)
        runner.clock.advance_to(runner.event.schedule.next_evaluation_at)
        with self.assertRaisesRegex(RuntimeError, "crash after send"):
            await runner.wake(WakeKind.DUE_EVALUATION, crash_after_send=True)
        self.assertEqual(len(runner.transport.messages), 1)

        recovered = await runner.recover_delivery()
        result = await runner.finish()
        self.assertEqual(recovered.trigger, "DELIVERY_RETRY")
        self.assertEqual(result.event.status, EventStatus.COMPLETED)
        self.assertEqual(result.transport_message_count, 1)
        self.assertEqual(result.delivery_count, 1)

    async def test_live_policy_calls_provider_only_for_model_owned_step(self) -> None:
        class SpyProvider:
            def __init__(self) -> None:
                self.calls = []

            def generate_json(self, system, user, temperature, max_tokens):
                self.calls.append((system, user, temperature, max_tokens))
                return '{"action":"SEND_NOW","reason_code":"context_due"}'

        fixture = self.fixtures_by_id()["l0_01"]
        provider = SpyProvider()
        result = await ScenarioRunnerV02.run_fixture(
            fixture, live_api=True, provider=provider
        )

        self.assertEqual(result.event.status, EventStatus.COMPLETED)
        self.assertEqual(len(provider.calls), 1)
        system_prompt, user_prompt, _, _ = provider.calls[0]
        combined = f"{system_prompt}\n{user_prompt}".casefold()
        self.assertNotIn('"oracle"', combined)
        self.assertNotIn('"expected_', combined)
        for constraint in fixture.oracle.hard_constraints:
            self.assertNotIn(constraint.casefold(), combined)
        trace = result.to_mapping()["traces"][0]
        self.assertEqual(trace["event_version_before"], 2)
        self.assertGreater(trace["event_version_after"], trace["event_version_before"])
        self.assertEqual(trace["decision_record"]["decision_id"], "decision-1")
        self.assertEqual(trace["delivery_audit"]["status"], "DELIVERED")
        self.assertEqual(
            trace["delivery_audit"]["idempotency_key"],
            f"{result.event.event_id}:send:3",
        )
        self.assertTrue(trace["delivery_audit"]["content_hash"].startswith("sha256:"))
        self.assertEqual(trace["provider_attempts"][0]["attempt"], 1)
        self.assertIsNone(trace["provider_attempts"][0]["validation_error"])

    async def test_live_policy_preserves_invalid_attempt_before_successful_retry(self) -> None:
        class RetryProvider:
            def __init__(self) -> None:
                self.outputs = iter((
                    '{"action":"NOT_ALLOWED","reason_code":"bad"}',
                    '{"action":"SEND_NOW","reason_code":"context_due"}',
                ))

            def generate_json(self, *args, **kwargs):
                return next(self.outputs)

        fixture = self.fixtures_by_id()["l0_01"]
        result = await ScenarioRunnerV02.run_fixture(
            fixture, live_api=True, provider=RetryProvider()
        )

        attempts = result.to_mapping()["traces"][0]["model_decision"]["attempts"]
        self.assertEqual([item["attempt"] for item in attempts], [1, 2])
        self.assertIn("unsupported action", attempts[0]["validation_error"])
        self.assertIsNone(attempts[1]["validation_error"])
        self.assertNotEqual(attempts[0]["prompt_hash"], attempts[1]["prompt_hash"])
        self.assertIn("NOT_ALLOWED", attempts[0]["raw_output"])
        self.assertIn("SEND_NOW", attempts[1]["raw_output"])

    async def test_live_policy_keeps_system_owned_step_deterministic(self) -> None:
        class FailingIfCalledProvider:
            def generate_json(self, *args, **kwargs):
                raise AssertionError("system-owned step must not call provider")

        fixture = self.fixtures_by_id()["l0_04"]
        result = await ScenarioRunnerV02.run_fixture(
            fixture, live_api=True, provider=FailingIfCalledProvider()
        )

        self.assertEqual(result.event.status, EventStatus.EXPIRED)
        self.assertEqual(result.traces[0].action, InitiativeAction.EXPIRE)

    async def test_live_provider_failure_is_reported_as_error(self) -> None:
        class BrokenProvider:
            def generate_json(self, *args, **kwargs):
                raise OSError("provider unavailable")

        fixture = self.fixtures_by_id()["l0_01"]
        with self.assertRaisesRegex(LivePolicyError, "live provider call failed") as caught:
            await ScenarioRunnerV02.run_fixture(
                fixture, live_api=True, provider=BrokenProvider()
            )
        partial = caught.exception.partial_result
        self.assertIsNotNone(partial)
        mapping = partial.to_mapping()
        self.assertEqual(mapping["event_status"], "SCHEDULED")
        self.assertEqual(mapping["cleanup_snapshot"], {
            "pending_wakeup_count": 0,
            "presence_subscription_count": 0,
            "active_lease_count": 0,
            "worker_task_count": 0,
        })
        self.assertEqual(len(mapping["traces"]), 1)
        failed_trace = mapping["traces"][0]
        self.assertIsNone(failed_trace["action"])
        self.assertIn("provider unavailable", failed_trace["error_message"])
        self.assertEqual(failed_trace["provider_attempts"][0]["attempt"], 1)
        self.assertIn(
            "provider_error: provider unavailable",
            failed_trace["provider_attempts"][0]["validation_error"],
        )

    async def test_live_failure_finally_cleans_existing_presence_subscription(self) -> None:
        class FailAfterWaitingProvider:
            def __init__(self) -> None:
                self.calls = 0

            def generate_json(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return (
                        '{"action":"WAIT_FOR_USER_ACTIVITY",'
                        '"reason_code":"wait_for_return"}'
                    )
                raise OSError("second decision unavailable")

        fixture = self.fixtures_by_id()["l1_02"]
        with self.assertRaises(LivePolicyError) as caught:
            await ScenarioRunnerV02.run_fixture(
                fixture, live_api=True, provider=FailAfterWaitingProvider()
            )

        partial = caught.exception.partial_result
        self.assertIsNotNone(partial)
        self.assertEqual(partial.cleanup.presence_subscription_count, 0)
        self.assertEqual(partial.cleanup.pending_wakeup_count, 0)
        self.assertEqual(len(partial.traces), 2)
        self.assertEqual(
            partial.traces[0].action, InitiativeAction.WAIT_FOR_USER_ACTIVITY
        )
        self.assertIsNotNone(partial.traces[1].error_message)


if __name__ == "__main__":
    unittest.main()
