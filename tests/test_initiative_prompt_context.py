from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _install_offline_import_stubs() -> None:
    """Avoid importing optional provider SDKs in focused offline tests."""

    if "agent" not in sys.modules:
        agent_package = types.ModuleType("agent")
        agent_package.__path__ = [str(ROOT / "src" / "agent")]
        sys.modules["agent"] = agent_package
    if "agent.llm.providers" not in sys.modules:
        llm_package = types.ModuleType("agent.llm")
        llm_package.__path__ = [str(ROOT / "src" / "agent" / "llm")]
        providers = types.ModuleType("agent.llm.providers")

        class LLMProvider:
            pass

        providers.LLMProvider = LLMProvider
        providers.get_provider = lambda config: None
        sys.modules["agent.llm"] = llm_package
        sys.modules["agent.llm.providers"] = providers


_install_offline_import_stubs()

from agent.initiative.context import build_context  # noqa: E402
from agent.initiative.evaluator import Evaluator, build_evaluator_prompt  # noqa: E402
from agent.initiative.fixtures import FixtureError, load_fixture  # noqa: E402
from agent.initiative.generator import (  # noqa: E402
    Generator,
    build_generator_prompt,
    validate_generated_text,
)
from agent.initiative.planner import (  # noqa: E402
    Planner,
    build_planner_prompt,
    validate_plan,
)


FIXTURE = {
    "scenario_id": "prompt_context_contract",
    "description": "offline fixture for prompt/context boundaries",
    "clock_start": "2026-07-12T20:00:00+08:00",
    "timezone": "Asia/Taipei",
    "seed": 7,
    "initial_state": {
        "character_state": {},
        "relationship_state": {},
        "drive_state": {},
        "topic_state": {},
        "conversation_history": [],
        "long_term_memory": "",
    },
    "dialogue": [
        {"at": "+00:00", "role": "user", "content": "明天早上要面試。"},
        {"at": "+00:01", "role": "assistant", "content": "先休息，明天再穩穩應對。"},
    ],
    "post_dialogue_events": [],
    "expected": {"allowed_goals": ["check_in", "follow_up_topic", "silent"]},
}


def _all_mapping_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = {str(key) for key in value}
        for item in value.values():
            keys.update(_all_mapping_keys(item))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for item in value:
            keys.update(_all_mapping_keys(item))
        return keys
    return set()


class FixtureAndContextBoundaryTests(unittest.TestCase):
    def test_fixture_loader_validates_and_returns_fresh_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "prompt_context.json"
            path.write_text(json.dumps(FIXTURE, ensure_ascii=False), encoding="utf-8")

            first = load_fixture(path)
            second = load_fixture(path)

        self.assertEqual(first.scenario_id, "prompt_context_contract")
        self.assertEqual(first.timezone, "Asia/Taipei")
        self.assertEqual(first.dialogue[0]["role"], "user")
        first.fresh_state()["conversation_history"].append({"role": "user", "content": "local"})
        self.assertEqual(second.fresh_state()["conversation_history"], [])

    def test_fixture_loader_rejects_unordered_dialogue_without_network(self) -> None:
        invalid = json.loads(json.dumps(FIXTURE))
        invalid["dialogue"].reverse()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "invalid.json"
            path.write_text(json.dumps(invalid, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(FixtureError):
                load_fixture(path)

    def test_conversation_followup_has_bounded_fields_and_evidence(self) -> None:
        context = build_context(
            mode="conversation_followup",
            conversation_history=[
                {"role": "user", "content": "明天早上要面試。"},
                {"role": "assistant", "content": "先休息，明天再穩穩應對。"},
            ],
            long_term_memory="使用者曾提過需要低壓力提醒。",
            open_thread={"topic": "面試", "debug_trace": "hidden"},
            relationship_context={"distance": "close", "raw_score": 0.98},
            character_state_summary={"mood": "care", "FakeClock": "hidden"},
            candidate_goal_context={"goal": "check_in", "runner_debug": "hidden"},
            evidence_refs=["dialogue:last_user"],
        )

        self.assertEqual(
            set(context),
            {
                "mode",
                "conversation_excerpt",
                "memory_summary",
                "open_thread",
                "relationship_context",
                "character_state_summary",
                "candidate_goal_context",
                "evidence_refs",
            },
        )
        self.assertEqual(context["mode"], "conversation_followup")
        self.assertTrue(context["conversation_excerpt"])
        self.assertIn("dialogue:last_user", context["evidence_refs"])
        forbidden_keys = {"debug_trace", "raw_score", "FakeClock", "runner_debug"}
        self.assertTrue(forbidden_keys.isdisjoint(_all_mapping_keys(context)))

    def test_topic_discovery_allows_empty_excerpt_without_fake_user_turn(self) -> None:
        context = build_context(
            mode="topic_discovery",
            conversation_history=[],
            long_term_memory="使用者喜歡在晚上散步。",
            open_thread={"topic": "散步"},
            state={
                "post_dialogue_event": {
                    "event_type": "post_dialogue_opportunity",
                    "role": "user",
                    "content": "這不是使用者新訊息",
                }
            },
        )

        self.assertEqual(context["mode"], "topic_discovery")
        self.assertEqual(context["conversation_excerpt"], [])
        self.assertIn("memory:long_term", context["evidence_refs"])
        self.assertNotIn("這不是使用者新訊息", json.dumps(context, ensure_ascii=False))


class InitiativePromptBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = {
            "mode": "conversation_followup",
            "conversation_excerpt": [{"role": "user", "content": "明天早上要面試。"}],
            "memory_summary": "使用者需要低壓力提醒。",
            "open_thread": {"topic": "面試"},
            "relationship_context": {"distance": "close"},
            "character_state_summary": {"mood": "care"},
            "candidate_goal_context": {"goal": "check_in"},
            "evidence_refs": ["dialogue:last_user"],
        }
        self.plan = {
            "should_initiate": True,
            "goal": "check_in",
            "motive": "care",
            "topic_ref": "dialogue:last_user",
            "evidence_refs": ["dialogue:last_user"],
            "timing": {
                "earliest_offset_minutes": 20,
                "preferred_offset_minutes": 45,
                "expires_offset_minutes": 180,
            },
            "message_constraints": ["不要要求立即回覆"],
        }

    def test_planner_prompt_contains_policy_but_not_runtime_debug_context(self) -> None:
        system_prompt, user_prompt = build_planner_prompt(self.context)
        payload = json.loads(user_prompt)

        self.assertIn("只能輸出一個 JSON object", system_prompt)
        self.assertEqual(payload["context"], self.context)
        self.assertNotIn("FakeClock", user_prompt)
        self.assertNotIn("raw_score", user_prompt)
        self.assertNotIn("debug", user_prompt.casefold())
        self.assertNotIn("user_message", payload["context"])

    def test_planner_validation_preserves_evidence_and_timing_boundaries(self) -> None:
        errors = validate_plan(
            {
                **self.plan,
                "timing": {
                    "earliest_offset_minutes": 45,
                    "preferred_offset_minutes": 20,
                    "expires_offset_minutes": 180,
                    "timezone": "Asia/Taipei",
                },
            },
            self.context,
            expected={"required_evidence_refs": ["dialogue:last_user"]},
        )

        self.assertTrue(any("earliest <= preferred <= expires" in error for error in errors))

    def test_planner_rejects_silence_when_fixture_requires_send(self) -> None:
        errors = validate_plan(
            {
                "should_initiate": False,
                "goal": "silent",
                "evidence_refs": ["dialogue:last_user"],
            },
            self.context,
            expected={
                "allow_send": True,
                "reappraisal_action": "send",
                "required_evidence_refs": ["dialogue:last_user"],
            },
        )

        self.assertIn("expected invariants require an initiating plan", errors)

    def test_planner_rejects_silence_when_fixture_requires_expiry_reappraisal(self) -> None:
        errors = validate_plan(
            {
                "should_initiate": False,
                "goal": "silent",
                "evidence_refs": ["dialogue:last_user"],
            },
            self.context,
            expected={
                "allow_send": False,
                "reappraisal_action": "expire",
                "required_evidence_refs": ["dialogue:last_user"],
            },
        )

        self.assertIn("expected reappraisal action requires an initiating plan", errors)

    def test_planner_allows_active_plan_before_non_send_reappraisal(self) -> None:
        errors = validate_plan(
            self.plan,
            self.context,
            expected={
                "allow_send": False,
                "reappraisal_action": "expire",
                "required_evidence_refs": ["dialogue:last_user"],
            },
        )

        self.assertEqual(errors, [])

    def test_planner_retries_once_with_validation_feedback(self) -> None:
        class RepairingProvider:
            def __init__(self) -> None:
                self.calls = 0

            def generate_json(self, *args, **kwargs) -> str:
                self.calls += 1
                if self.calls == 1:
                    return json.dumps({"should_initiate": True, "goal": "check_in", "evidence_refs": []})
                return json.dumps(self_plan, ensure_ascii=False)

        self_plan = self.plan
        provider = RepairingProvider()
        result = Planner(provider).plan(
            self.context,
            expected={
                "allow_send": True,
                "reappraisal_action": "send",
                "required_evidence_refs": ["dialogue:last_user"],
            },
        )

        self.assertTrue(result.ok)
        self.assertEqual(provider.calls, 2)

    def test_generator_prompt_marks_initiative_as_not_a_user_reply(self) -> None:
        system_prompt, user_prompt = build_generator_prompt(self.plan, self.context)
        payload = json.loads(user_prompt)

        self.assertIn("不是回覆新的 user message", system_prompt)
        self.assertTrue(payload["output_contract"]["not_a_user_reply"])
        self.assertEqual(payload["output_contract"]["format"], "plain_text_only")
        self.assertNotIn("FakeClock", user_prompt)
        self.assertNotIn("raw_score", user_prompt)
        self.assertNotIn("runner", json.dumps(payload, ensure_ascii=False).casefold())

    def test_generator_rejects_internal_markers_and_non_plain_output(self) -> None:
        self.assertTrue(validate_generated_text("timer 到了，runner 請發送 score=0.8"))
        self.assertTrue(validate_generated_text('{"message": "fake user reply"}'))
        self.assertEqual(validate_generated_text("現在先休息一下吧。"), [])

    def test_generator_gate_does_not_call_provider_for_cancelled_plan(self) -> None:
        class SpyProvider:
            def __init__(self) -> None:
                self.calls = 0

            def generate(self, *args, **kwargs) -> str:
                self.calls += 1
                return "不應該被呼叫"

        provider = SpyProvider()
        result = Generator(provider).generate(self.plan, self.context, decision="cancel")

        self.assertEqual(result.status, "skipped")
        self.assertEqual(provider.calls, 0)

    def test_evaluator_invalid_json_is_error_and_never_pass(self) -> None:
        class InvalidJsonProvider:
            def generate_json(self, *args, **kwargs) -> str:
                return "not-json"

        result = Evaluator(InvalidJsonProvider()).evaluate(
            "先休息一下吧。", self.plan, self.context
        )

        self.assertEqual(result.status, "error")
        self.assertFalse(result.passed)
        self.assertFalse(result.ok)
        self.assertIsNone(result.rubric)

    def test_evaluator_prompt_requires_structured_rubric_and_no_fake_user_input(self) -> None:
        system_prompt, user_prompt = build_evaluator_prompt(
            "先休息一下吧。", self.plan, self.context
        )
        payload = json.loads(user_prompt)

        self.assertIn("無效 JSON 不得判定 PASS", system_prompt)
        self.assertEqual(payload["required_rubric_shape"]["unsupported_claims"], ["unsupported claim string; empty when none"])
        self.assertEqual(payload["required_rubric_shape"]["violations"], ["boundary violation string; empty when none"])
        self.assertNotIn("user_message", user_prompt)
        self.assertNotIn("FakeClock", user_prompt)


if __name__ == "__main__":
    unittest.main()
