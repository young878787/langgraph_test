from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# The legacy package initializer imports optional provider SDKs.  These focused
# tests only need logger and initiative modules, so keep their import boundary
# offline without changing runtime package behavior.
if "agent" not in sys.modules:
    agent_package = types.ModuleType("agent")
    agent_package.__path__ = [str(ROOT / "src" / "agent")]
    sys.modules["agent"] = agent_package

from agent import logger  # noqa: E402
from agent.initiative import (  # noqa: E402
    FakeClock,
    InitiativePlan,
    PlanGoal,
    PlanTiming,
    PostDialogueOpportunity,
    ReappraisalContext,
    TimingValidationError,
    can_generate,
    check_plan,
    reappraise,
    validate_plan,
)


TZ = timezone(timedelta(hours=8))
OBSERVED_AT = datetime(2026, 7, 12, 20, 0, tzinfo=TZ)


_FIXTURE_JSON = """
{
  "scenario_id": "delayed_care_after_rest",
  "clock_start": "2026-07-12T20:00:00+08:00",
  "timezone": "Asia/Taipei",
  "dialogue": [
    {"at": "+00:00", "role": "user", "content": "今天工作好多。"},
    {"at": "+00:04", "role": "assistant", "content": "去休息啦，剩下的晚點再說。"}
  ],
  "initial_state": {
    "character_state": {},
    "relationship_state": {},
    "drive_state": {},
    "topic_state": {},
    "conversation_history": [],
    "long_term_memory": ""
  },
  "expected": {
    "allowed_goals": ["check_in", "follow_up_topic", "silent"],
    "required_evidence_refs": ["dialogue:last_user"],
    "forbidden_goals": ["demand_reply"]
  }
}
"""


def load_fixture() -> dict:
    """Load an isolated contract fixture without touching shared fixture files."""

    return json.loads(_FIXTURE_JSON)


def make_plan(
    *,
    plan_id: str = "plan-1",
    scenario_id: str = "delayed_care_after_rest",
    goal: str = "check_in",
    timing: PlanTiming | None = None,
    evidence_refs: tuple[str, ...] = ("dialogue:last_user",),
) -> InitiativePlan:
    return InitiativePlan(
        plan_id=plan_id,
        scenario_id=scenario_id,
        goal=goal,
        topic_ref="dialogue:last_user",
        evidence_refs=evidence_refs,
        timing=timing or PlanTiming.from_offsets(OBSERVED_AT, earliest=10, preferred=20, expires=40),
        motive="care",
        timing_reason="先讓使用者休息，再低壓力關心",
        message_constraints=("不要診斷", "不要要求立即回覆"),
    )


class InitiativeFixtureAndPlanContractTests(unittest.TestCase):
    def test_fixture_loader_returns_complete_independent_fixture(self) -> None:
        first = load_fixture()
        second = load_fixture()

        self.assertEqual(first["dialogue"][-1]["role"], "assistant")
        self.assertIn("conversation_history", first["initial_state"])
        self.assertEqual(first["timezone"], "Asia/Taipei")
        first["dialogue"].append({"role": "user", "content": "local mutation"})
        self.assertEqual(len(second["dialogue"]), 2)

    def test_valid_plan_preserves_evidence_provenance(self) -> None:
        plan = make_plan()

        self.assertIs(validate_plan(plan, available_evidence_refs={"dialogue:last_user"}), plan)
        self.assertTrue(
            check_plan(plan, available_evidence_refs={"dialogue:last_user"}).valid
        )

    def test_unknown_evidence_is_rejected(self) -> None:
        plan = make_plan(evidence_refs=("dialogue:not_in_context",))

        result = check_plan(plan, available_evidence_refs={"dialogue:last_user"})

        self.assertFalse(result.valid)
        self.assertIn("unknown_evidence_ref", {issue.code for issue in result.issues})

    def test_forbidden_goal_is_rejected(self) -> None:
        plan = make_plan(goal=PlanGoal.DEMAND_REPLY.value)

        result = check_plan(plan)

        self.assertFalse(result.valid)
        self.assertIn("forbidden_goal", {issue.code for issue in result.issues})

    def test_timing_order_and_timezone_are_hard_contracts(self) -> None:
        with self.assertRaises(TimingValidationError):
            PlanTiming.from_offsets(OBSERVED_AT, earliest=20, preferred=10, expires=40)
        with self.assertRaises(TimingValidationError):
            PlanTiming.from_offsets(datetime(2026, 7, 12, 20, 0), earliest=0, preferred=1, expires=2)

    def test_post_dialogue_opportunity_is_not_a_user_message(self) -> None:
        event = PostDialogueOpportunity(
            observed_at=OBSERVED_AT,
            last_dialogue_at=OBSERVED_AT - timedelta(minutes=4),
        )

        self.assertEqual(event.event_type, "post_dialogue_opportunity")
        self.assertEqual(event.source, "test_harness")
        self.assertFalse(hasattr(event, "role"))
        self.assertFalse(hasattr(event, "content"))


class FakeClockAndReappraisalContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock(OBSERVED_AT)
        self.plan = make_plan()

    def test_fake_clock_advances_without_sleep_and_rejects_backwards(self) -> None:
        self.assertEqual(self.clock.advance_by(timedelta(minutes=20)), self.plan.timing.preferred_at)
        with self.assertRaises(ValueError):
            self.clock.advance_to(OBSERVED_AT - timedelta(seconds=1))

    def test_new_user_message_cancels_plan_before_generator_gate(self) -> None:
        decision = reappraise(
            self.plan,
            self.plan.timing.preferred_at,
            ReappraisalContext(has_new_user_message=True),
        )

        self.assertEqual(decision.action, "cancel")
        self.assertEqual(decision.reason, "new_user_message")
        self.assertFalse(can_generate(decision))

    def test_expired_plan_does_not_generate(self) -> None:
        decision = reappraise(self.plan, self.plan.timing.expires_at)

        self.assertEqual((decision.action, decision.reason), ("expire", "expired"))
        self.assertFalse(can_generate(decision))

    def test_duplicate_and_dnd_plans_are_suppressed(self) -> None:
        duplicate = reappraise(
            self.plan,
            self.plan.timing.preferred_at,
            ReappraisalContext(duplicate=True),
        )
        dnd = reappraise(
            self.plan,
            self.plan.timing.preferred_at,
            ReappraisalContext(do_not_disturb=True),
        )

        self.assertEqual((duplicate.action, duplicate.reason), ("suppress", "duplicate"))
        self.assertEqual((dnd.action, dnd.reason), ("suppress", "do_not_disturb"))
        self.assertFalse(can_generate(duplicate))
        self.assertFalse(can_generate(dnd))

    def test_generator_only_opens_at_preferred_time(self) -> None:
        before_earliest = reappraise(self.plan, self.plan.timing.earliest_at - timedelta(seconds=1))
        before_preferred = reappraise(self.plan, self.plan.timing.preferred_at - timedelta(seconds=1))
        at_preferred = reappraise(self.plan, self.plan.timing.preferred_at)

        self.assertEqual(before_earliest.reason, "before_earliest")
        self.assertEqual(before_preferred.reason, "before_preferred")
        self.assertFalse(can_generate(before_earliest))
        self.assertFalse(can_generate(before_preferred))
        self.assertEqual(at_preferred.action, "send")
        self.assertTrue(can_generate(at_preferred))


class InitiativeLoggerContractTests(unittest.TestCase):
    def test_new_run_initializes_once_and_scenarios_append(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            with patch.object(logger, "LOG_DIR", log_dir), patch.object(
                logger, "ERROR_LOG", log_dir / "error.log"
            ), patch.object(logger, "PROMPT_MD", log_dir / "prompts.md"), patch.object(
                logger, "MEMORY_MD", log_dir / "memory.md"
            ):
                logger.init_logs()
                logger.log_initiative_trace(
                    "run-1",
                    "scenario-a",
                    {
                        "result": "PASS",
                        "scenario_elapsed_ms": 1234.5,
                        "scenario": {
                            "description": "休息後低壓力關心",
                            "provider_backend": "google",
                            "model": "test-model",
                        },
                        "gates": [{"name": "planner", "ok": True, "summary": "valid plan"}],
                        "plan": {"goal": "check_in"},
                        "initial_state": {"detail_marker": "must-not-be-logged"},
                    },
                    timestamp="2026-07-12T20:00:00+08:00",
                )
                logger.log_initiative_trace(
                    "run-1",
                    "scenario-b",
                    {
                        "result": "FAIL",
                        "primary_reason": "planner contract validation failed: should_initiate must be boolean",
                        "gates": [{"name": "evaluator", "ok": False, "summary": "score below threshold"}],
                        "errors": ["rubric validation failed"],
                    },
                    timestamp="2026-07-12T20:01:00+08:00",
                )
                logger.log_initiative_summary(
                    [
                        {
                            "scenario_id": "scenario-a",
                            "status": "PASS",
                            "gates": [{"name": "planner", "ok": True, "summary": "valid plan"}],
                            "trace": {"scenario": {"description": "休息後低壓力關心"}},
                        },
                        {
                            "scenario_id": "scenario-b",
                            "status": "FAIL",
                            "gates": [
                                {"name": "evaluator", "ok": False, "summary": "score below threshold"}
                            ],
                            "trace": {
                                "scenario": {"description": "評分不足案例"},
                                "primary_reason": "planner contract validation failed: should_initiate must be boolean",
                            },
                        },
                    ]
                )

                content = (log_dir / "prompts.md").read_text(encoding="utf-8")

        self.assertEqual(content.count("# 📝 Prompts 日誌"), 1)
        self.assertEqual(content.count("測試："), 2)
        self.assertLess(content.index("scenario-a"), content.index("scenario-b"))
        self.assertIn("[PASS] 測試：休息後低壓力關心", content)
        self.assertIn("**單情境完整耗時**: 1.23 秒", content)
        self.assertIn("[FAIL] 測試：scenario-b", content)
        self.assertIn("rubric validation failed", content)
        self.assertIn("| FAIL | evaluator | score below threshold |", content)
        self.assertNotIn("must-not-be-logged", content)
        self.assertIn("## Initiative 測試總覽", content)
        self.assertIn("共 **2** 個測試", content)
        self.assertIn("✅ PASS **1**", content)
        self.assertIn("❌ FAIL **1**", content)
        self.assertIn("主要原因", content)
        self.assertIn("should_initiate must be boolean", content)
        self.assertIn("| 2 | ❌ **FAIL** | 評分不足案例 | `scenario-b` | planner contract validation failed: should_initiate must be boolean |", content)
        self.assertLess(content.index("## Initiative 測試總覽"), content.index("[PASS] 測試："))


if __name__ == "__main__":
    unittest.main()
