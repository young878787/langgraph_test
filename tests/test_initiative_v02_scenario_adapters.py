from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
if "agent" not in sys.modules:
    agent_package = types.ModuleType("agent")
    agent_package.__path__ = [str(ROOT / "src" / "agent")]
    sys.modules["agent"] = agent_package

from agent.initiative.adapters import (  # noqa: E402
    GraphDialogueAdapter, LegacyDialogueAdapter, MockMemoryAdapter, MockMessageAdapter,
    MockPresenceAdapter, MockSessionAdapter, PresenceSubscription,
)
from agent.initiative.scenario import (  # noqa: E402
    ScenarioError, ScenarioObservation, build_report, fixture_from_mapping,
    load_scenarios,
)


FIXTURES = ROOT / "tests" / "fixtures" / "initiative_v02" / "core_scenarios.json"


def test_core_fixture_distribution_and_oracle_isolation() -> None:
    fixtures = load_scenarios(FIXTURES)
    assert len(fixtures) == 10
    assert Counter(item.model.category for item in fixtures) == {
        "L0": 5, "L1": 1, "L2": 2,
        "cross_session_presence": 1, "delivery_recovery": 1,
    }
    for fixture in fixtures:
        assert fixture.model.title
        assert fixture.model.purpose
        assert fixture.model.prelude
        assert fixture.model.timeline
        assert fixture.oracle.expected_steps
        assert fixture.oracle.expected_final.event_status in {
            "COMPLETED", "CANCELLED", "EXPIRED", "SILENCED",
        }
        assert fixture.oracle.expected_event_count == fixture.oracle.expected_final.event_count
        payload = json.dumps(fixture.model.to_payload(), ensure_ascii=False).casefold()
        assert "expected_action" not in payload
        assert "hard_constraints" not in payload
        assert "soft_preferences" not in payload
        assert "purpose" not in payload
        assert "timeline" not in payload
        assert fixture.driver.steps or fixture.harness.steps

    precedence = next(item for item in fixtures if item.model.scenario_id == "core_07_expired_event")
    assert precedence.oracle.expected_action == "EXPIRE"
    assert precedence.oracle.expected_steps[0].decision_owner == "system"
    assert precedence.oracle.expected_final.event_status == "EXPIRED"


def test_fixture_validation_rejects_invalid_contract_before_model_payload() -> None:
    raw = json.loads(FIXTURES.read_text(encoding="utf-8"))[0]
    invalid_cases = []

    bad_version = deepcopy(raw)
    bad_version["schema_version"] = 1
    invalid_cases.append(bad_version)

    duplicate_step = deepcopy(raw)
    duplicate_step["timeline"][0]["step_id"] = duplicate_step["prelude"][0]["step_id"]
    invalid_cases.append(duplicate_step)

    naive_clock = deepcopy(raw)
    naive_clock["clock_start"] = "2026-07-13T10:00:00"
    invalid_cases.append(naive_clock)

    invalid_action = deepcopy(raw)
    invalid_action["oracle"]["expected_steps"][0]["expected_action"] = "RETRY"
    invalid_cases.append(invalid_action)

    incomplete_final = deepcopy(raw)
    del incomplete_final["oracle"]["expected_final"]["worker_task_count"]
    invalid_cases.append(incomplete_final)

    for invalid in invalid_cases:
        with unittest.TestCase().assertRaises(ScenarioError):
            fixture_from_mapping(invalid)


def test_timeline_timestamps_must_be_ordered() -> None:
    raw = json.loads(FIXTURES.read_text(encoding="utf-8"))[0]
    raw["timeline"] = [
        {"step_id": "t1", "type": "advance_clock", "at": "2026-07-13T10:10:00+08:00", "minutes": 5},
        {"step_id": "t2", "type": "advance_clock", "at": "2026-07-13T10:05:00+08:00", "minutes": 5},
    ]
    with unittest.TestCase().assertRaises(ScenarioError):
        fixture_from_mapping(raw)


def test_dialogue_adapter_rejects_oracle_and_scheduler_state() -> None:
    adapter = LegacyDialogueAdapter(lambda state: state["text"])
    assert adapter.respond({"text": "ok"}) == "ok"
    with unittest.TestCase().assertRaises(ValueError):
        adapter.respond({"text": "no", "expected": {"action": "SEND_NOW"}})
    with unittest.TestCase().assertRaises(ValueError):
        adapter.respond({"text": "no", "scheduler": object()})


def test_driver_and_harness_views_split_fault_controls() -> None:
    fixture = next(item for item in load_scenarios(FIXTURES) if item.model.scenario_id == "core_09_exactly_once_recovery")
    driver_types = {item.type for item in fixture.driver.steps}
    harness_types = {item.type for item in fixture.harness.steps}
    assert not driver_types & {"inject_fault", "duplicate_wakeup", "start_competing_worker"}
    assert harness_types <= {"seed_via_factory", "activate_event", "deliver_once", "inject_fault", "duplicate_wakeup", "start_competing_worker"}
    assert len(fixture.driver.steps) + len(fixture.harness.steps) == (
        len(fixture.model.prelude) + len(fixture.model.timeline)
    )


def test_graph_dialogue_adapter_runs_complete_graph_and_retains_state() -> None:
    class FakeGraph:
        def invoke(self, state):
            updated = dict(state)
            history = list(updated.get("conversation_history", []))
            history.extend((
                {"role": "user", "content": updated["user_input"]},
                {"role": "assistant", "content": f"角色回覆:{updated['user_input']}"},
            ))
            updated["conversation_history"] = history
            updated["response"] = history[-1]["content"]
            return updated

    with patch("agent.graph.build_graph", return_value=FakeGraph()), patch(
        "agent.graph.new_state", return_value={"conversation_history": []}
    ):
        adapter = GraphDialogueAdapter()
        assert adapter.respond({"user_input": "第一輪", "turn_id": "u1"}) == "角色回覆:第一輪"
        assert adapter.respond({"user_input": "第二輪", "turn_id": "u2"}) == "角色回覆:第二輪"
        assert len(adapter.state["conversation_history"]) == 4
        with unittest.TestCase().assertRaises(ValueError):
            adapter.respond({"user_input": "不可見", "oracle": {"expected_action": "SEND_NOW"}})


def test_session_and_memory_are_world_scoped_and_copied() -> None:
    sessions = MockSessionAdapter()
    sessions.save("w1", "s1", {"turn": 1})
    assert sessions.load("w1", "s1") == {"turn": 1}
    assert sessions.load("w2", "s1") is None
    memories = MockMemoryAdapter()
    memories.append("w1", "u1", {"fact": "a"})
    assert memories.recall("w1", "u1") == ({"fact": "a"},)
    assert memories.recall("w2", "u1") == ()


def test_presence_signal_and_independent_expiry_wakeup() -> None:
    now = datetime(2026, 7, 13, 10, tzinfo=timezone.utc)
    adapter = MockPresenceAdapter()
    adapter.subscribe(PresenceSubscription("sub1", "w1", "u1", "evt1", now + timedelta(hours=1)))
    assert adapter.signal("w1", "u1", now) == ("evt1",)
    assert adapter.signal("w2", "u1", now) == ()
    assert adapter.expire(now + timedelta(hours=1)) == ("evt1",)
    assert adapter.subscriptions == ()


def test_message_adapter_is_observably_exactly_once() -> None:
    adapter = MockMessageAdapter()
    first = adapter.send("console:u1", "hello", "evt1:send:1")
    second = adapter.send("console:u1", "hello", "evt1:send:1")
    assert first == second
    assert len(adapter.deliveries) == 1
    with unittest.TestCase().assertRaises(ValueError):
        adapter.send("console:u1", "changed", "evt1:send:1")


def test_report_keeps_plumbing_model_and_soft_quality_separate() -> None:
    fixtures = load_scenarios(FIXTURES)[:2]
    observations = [
        ScenarioObservation(fixtures[0].model.scenario_id, fixtures[0].oracle.expected_action, soft_scores={"naturalness": 4}),
        ScenarioObservation(fixtures[1].model.scenario_id, "CANCEL", deliveries=2, hard_violations=("duplicate",)),
    ]
    report = build_report(fixtures, observations)
    assert set(report) == {"plumbing_result", "model_decision_result", "soft_quality_result"}
    assert report["plumbing_result"]["passed"] == 1
    assert report["plumbing_result"]["duplicate_deliveries"] == 1
    assert report["model_decision_result"]["correct"] == 1
    assert report["soft_quality_result"]["averages"]["naturalness"] == 4


class ScenarioAdapterTests(unittest.TestCase):
    def test_core_fixtures(self) -> None:
        test_core_fixture_distribution_and_oracle_isolation()

    def test_dialogue_boundary(self) -> None:
        test_dialogue_adapter_rejects_oracle_and_scheduler_state()

    def test_graph_dialogue_boundary(self) -> None:
        test_graph_dialogue_adapter_runs_complete_graph_and_retains_state()

    def test_driver_harness_split(self) -> None:
        test_driver_and_harness_views_split_fault_controls()

    def test_fixture_validation(self) -> None:
        test_fixture_validation_rejects_invalid_contract_before_model_payload()

    def test_timeline_ordering(self) -> None:
        test_timeline_timestamps_must_be_ordered()

    def test_world_scoping(self) -> None:
        test_session_and_memory_are_world_scoped_and_copied()

    def test_presence_expiry(self) -> None:
        test_presence_signal_and_independent_expiry_wakeup()

    def test_exactly_once_message_adapter(self) -> None:
        test_message_adapter_is_observably_exactly_once()

    def test_split_report(self) -> None:
        test_report_keeps_plumbing_model_and_soft_quality_separate()


if __name__ == "__main__":
    unittest.main()
