from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import replace
import json
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
    PolicyDecision,
    ScenarioRunnerV02,
    SequencePolicy,
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

    async def test_fixture_replay_has_no_deterministic_oracle_fallback(self) -> None:
        fixture = self.fixtures_by_id()["core_01_commitment_followup"]
        with self.assertRaisesRegex(ValueError, "live-model-only"):
            await ScenarioRunnerV02.run_fixture(fixture)

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

    async def test_driver_drains_event_due_before_later_external_clock_step(self) -> None:
        fixture = self.fixtures_by_id()["core_01_commitment_followup"]
        runner = make_runner(PolicyDecision(InitiativeAction.SEND_NOW, "context_due"))
        create(runner)

        await runner._execute_driver_lifecycle(fixture)
        result = await runner.finish()

        self.assertEqual(runner.event.status, EventStatus.COMPLETED)
        self.assertEqual(result.traces[0].logical_time, NOW + timedelta(minutes=5))

    async def test_timeline_user_message_runs_dialogue_hook_before_reappraisal(self) -> None:
        fixture = self.fixtures_by_id()["core_05_resolved_before_trigger"]
        runner = make_runner(PolicyDecision(InitiativeAction.CANCEL, "resolved"))
        create(runner)
        seen = []

        await runner._execute_driver_lifecycle(
            fixture,
            process_dialogue_turn=lambda step_id, text: seen.append((step_id, text)),
        )

        self.assertEqual(seen, [("t1", "不用提醒了，我剛剛已經自己處理好了。")])
        self.assertEqual(runner.event.status, EventStatus.CANCELLED)

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

    async def test_live_e2e_runs_all_stages_and_delivers_generator_text(self) -> None:
        class Dialogue:
            def respond(self, model_input):
                self.last_input = dict(model_input)
                return "好，我晚點會接著陪你聊。"

        class ScriptedProvider:
            model = "test-live-model"

            def __init__(self):
                self.prompts = []

            def generate_json(self, system, user, temperature, max_output_tokens):
                self.prompts.append((system, user))
                payload = json.loads(user)
                if "candidate_scan" in system:
                    return json.dumps({
                        "schema_version": "initiative.world_event_proposal.v1",
                        "decision_type": "candidate_scan",
                        "events": [{
                            "candidate_id": "candidate:1",
                            "event_type": "commitment",
                            "summary": "稍後續接剛才的對話",
                            "evidence_refs": ["turn:u1", "turn:a1"],
                            "followup_value": "履行已形成的續聊承諾",
                            "interruption_risk": "low",
                            "trigger": {
                                "kind": "time", "earliest_offset_minutes": 0,
                                "preferred_offset_minutes": 60, "expires_offset_minutes": 120,
                            },
                            "confidence": 0.9,
                            "short_rationale": "對話中有明確的稍後續接承諾",
                        }],
                        "no_event_reason": None,
                    }, ensure_ascii=False)
                if "candidate_consolidation" in system:
                    return json.dumps({
                        "schema_version": "initiative.world_event_consolidation.v1",
                        "decision_type": "candidate_consolidation",
                        "accepted_candidate_ids": ["candidate:1"],
                        "merged_candidates": [], "rejected_candidates": [],
                        "short_rationale": "承諾仍未完成",
                    }, ensure_ascii=False)
                event = payload["runtime"]["active_events"][0]
                return json.dumps({
                    "schema_version": "initiative.reappraisal.v1",
                    "decision_type": "wake_up_reappraisal",
                    "event_id": event["event_id"], "event_version": event["event_version"],
                    "action": "SEND_NOW", "reason_code": "followup_still_relevant",
                    "evidence_refs": ["turn:u1", "turn:a1"],
                    "next_evaluation_offset_minutes": None,
                    "short_rationale": "目前適合低壓續接",
                }, ensure_ascii=False)

            def generate(self, system, user, temperature, max_output_tokens):
                return "飯煮好了嗎？不急，我只是來把剛才的話題接回來。"

        fixture = self.fixtures_by_id()["core_01_commitment_followup"]
        provider = ScriptedProvider()
        result = await ScenarioRunnerV02.run_fixture(
            fixture, live_api=True, provider=provider, dialogue_adapter=Dialogue()
        )
        mapping = result.to_mapping()
        self.assertEqual(result.event.status, EventStatus.COMPLETED)
        self.assertEqual(mapping["initiative_message"], "飯煮好了嗎？不急，我只是來把剛才的話題接回來。")
        self.assertNotEqual(mapping["initiative_message"], result.event.summary)
        self.assertEqual(
            [item["stage"] for item in mapping["call_ledger"]],
            ["dialogue_response", "candidate_scan", "candidate_consolidation", "reappraisal", "generator"],
        )
        combined = "\n".join(system + user for system, user in provider.prompts).casefold()
        self.assertNotIn('"oracle"', combined)
        self.assertNotIn('"purpose"', combined)
        self.assertEqual(mapping["flow_result"], "PASS")
        self.assertEqual(mapping["human_review"], "PENDING")

    async def test_oracle_mutation_does_not_change_live_runtime(self) -> None:
        fixture = self.fixtures_by_id()["core_01_commitment_followup"]
        mutated_oracle = replace(fixture.oracle, expected_action="CANCEL")
        mutated = replace(fixture, oracle=mutated_oracle)
        self.assertEqual(fixture.model.to_payload(), mutated.model.to_payload())
        self.assertEqual(fixture.driver, mutated.driver)


if __name__ == "__main__":
    unittest.main()
