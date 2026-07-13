from __future__ import annotations

import json
import sys
from tempfile import TemporaryDirectory
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent.config import AgentConfig  # noqa: E402
from agent import logger  # noqa: E402
from agent.initiative.evaluator import Evaluator  # noqa: E402
from agent.initiative.fixtures import load_fixture, load_fixtures  # noqa: E402
from agent.initiative.generator import Generator  # noqa: E402
from agent.initiative.planner import Planner, PlannerResult  # noqa: E402
from agent.initiative.runner import InitiativeRunner  # noqa: E402


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "initiative"


class _ReplayGraph:
    def invoke(self, state: dict) -> dict:
        updated = dict(state)
        history = list(updated.get("conversation_history", []))
        history.extend(
            [
                {"role": "user", "content": updated.get("user_input", "")},
                {"role": "assistant", "content": "fixture graph response"},
            ]
        )
        updated["conversation_history"] = history
        updated["response"] = "fixture graph response"
        return updated


class _StageProvider:
    def generate(self, system_prompt: str, user_prompt: str, temperature: float, max_output_tokens=None) -> str:
        if "initiative Generator" in system_prompt:
            return "剛剛想到你提過的事，晚點再回也沒關係。"
        return "fixture graph response"

    def generate_json(self, system_prompt: str, user_prompt: str, temperature: float, max_output_tokens=None) -> str:
        if "initiative Planner" in system_prompt:
            return json.dumps(
                {
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
                    "timing_reason": "尊重休息時間",
                    "message_constraints": ["不要要求立即回覆"],
                },
                ensure_ascii=False,
            )
        if "initiative Evaluator" in system_prompt:
            return json.dumps(
                {
                    "goal_alignment": 1.0,
                    "context_grounding": 1.0,
                    "character_consistency": 1.0,
                    "timing_reasonableness": 1.0,
                    "intrusiveness": 1.0,
                    "unsupported_claims": [],
                    "violations": [],
                    "pass": True,
                    "reason": "bounded fake-provider evaluation",
                },
                ensure_ascii=False,
            )
        return "{}"


class _InvalidPlanner:
    def plan(self, context: dict, *, expected: dict) -> PlannerResult:
        return PlannerResult(
            status="error",
            error="invalid planner result",
            raw_output='{"should_initiate":"yes","goal":"unknown"}',
            validation_errors=[
                "should_initiate must be boolean",
                "goal is not an allowed initiative enum",
            ],
        )


class InitiativeRunnerIntegrationTests(unittest.TestCase):
    def test_all_fixtures_pass_offline_without_external_delivery(self) -> None:
        fixtures = load_fixtures(FIXTURE_DIR)
        traces: list[dict] = []
        runner = InitiativeRunner(log_writer=traces.append)

        results = runner.run_many(fixtures)

        self.assertEqual(len(results), 9)
        self.assertTrue(all(result.status == "PASS" for result in results))
        self.assertTrue(all(result.trace.get("scenario_elapsed_ms", 0) >= 0 for result in results))
        self.assertEqual(len(traces), len(results))
        trace_payloads = [trace["trace"] for trace in traces]
        self.assertTrue(all("planner_prompt" in trace for trace in trace_payloads))
        self.assertTrue(all("evaluator_raw" not in trace or "result" in trace for trace in trace_payloads))
        expired = next(result for result in results if result.scenario_id == "expired_context")
        self.assertTrue(expired.plan.should_initiate)
        self.assertEqual(expired.decision.action, "expire")
        self.assertNotIn("generator_raw", expired.trace)

    def test_injected_planner_generator_evaluator_use_typed_results(self) -> None:
        provider = _StageProvider()
        config = AgentConfig(backend="mock")
        traces: list[dict] = []
        runner = InitiativeRunner(
            config,
            provider=provider,
            planner=Planner(provider, config=config),
            generator=Generator(provider, config=config),
            evaluator=Evaluator(provider, config=config),
            graph_builder=lambda _config: _ReplayGraph(),
            log_writer=traces.append,
        )

        result = runner.run_fixture(load_fixture(FIXTURE_DIR / "delayed_care_after_rest.json"))

        self.assertEqual(result.status, "PASS")
        self.assertIn("想到你提過", result.initiative_message)
        self.assertEqual(result.decision.action, "send")
        self.assertIn("planner_raw", result.trace)
        self.assertIn("generator_raw", result.trace)
        self.assertIn("evaluator_raw", result.trace)

    def test_expired_context_retries_transient_silent_planner_output(self) -> None:
        class RepairingProvider(_StageProvider):
            def __init__(self) -> None:
                self.planner_calls = 0

            def generate_json(self, system_prompt: str, user_prompt: str, temperature: float, max_output_tokens=None) -> str:
                if "initiative Planner" in system_prompt:
                    self.planner_calls += 1
                    if self.planner_calls == 1:
                        return json.dumps(
                            {
                                "should_initiate": False,
                                "goal": "silent",
                                "evidence_refs": ["dialogue:last_user"],
                            },
                            ensure_ascii=False,
                        )
                return super().generate_json(system_prompt, user_prompt, temperature, max_output_tokens)

        provider = RepairingProvider()
        runner = InitiativeRunner(
            AgentConfig(backend="mock"),
            provider=provider,
            graph_builder=lambda _config: _ReplayGraph(),
            log_writer=lambda _trace: None,
        )

        result = runner.run_fixture(load_fixture(FIXTURE_DIR / "expired_context.json"))

        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.decision.action, "expire")
        self.assertEqual(provider.planner_calls, 2)
        self.assertNotIn("generator_raw", result.trace)

    def test_live_api_rejects_mock_backend_as_error(self) -> None:
        traces: list[dict] = []
        runner = InitiativeRunner(
            AgentConfig(backend="mock"),
            live_api=True,
            log_writer=traces.append,
        )

        result = runner.run_fixture(load_fixture(FIXTURE_DIR / "delayed_care_after_rest.json"))

        self.assertEqual(result.status, "ERROR")
        self.assertFalse(result.initiative_message)
        self.assertIn("--live-api requires a non-mock backend", result.trace["errors"])

    def test_planner_failure_keeps_raw_output_and_primary_reason_in_trace(self) -> None:
        traces: list[dict] = []
        runner = InitiativeRunner(
            AgentConfig(backend="mock"),
            planner=_InvalidPlanner(),
            graph_builder=lambda _config: _ReplayGraph(),
            log_writer=traces.append,
        )

        result = runner.run_fixture(load_fixture(FIXTURE_DIR / "expired_context.json"))

        self.assertEqual(result.status, "ERROR")
        self.assertEqual(result.trace["failure"]["stage"], "planner")
        self.assertEqual(
            result.trace["planner_validation_errors"],
            [
                "should_initiate must be boolean",
                "goal is not an allowed initiative enum",
            ],
        )
        self.assertIn("should_initiate", result.trace["primary_reason"])
        self.assertEqual(
            result.trace["planner_raw"],
            '{"should_initiate":"yes","goal":"unknown"}',
        )
        self.assertNotIn("generator_raw", result.trace)

    def test_planner_failure_is_written_to_prompts_log_with_raw_output(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            with patch.object(logger, "LOG_DIR", log_dir), patch.object(
                logger, "ERROR_LOG", log_dir / "error.log"
            ), patch.object(logger, "PROMPT_MD", log_dir / "prompts.md"), patch.object(
                logger, "MEMORY_MD", log_dir / "memory.md"
            ):
                logger.init_logs()
                runner = InitiativeRunner(
                    AgentConfig(backend="mock"),
                    planner=_InvalidPlanner(),
                    graph_builder=lambda _config: _ReplayGraph(),
                )
                runner.run_fixture(load_fixture(FIXTURE_DIR / "expired_context.json"))
                content = (log_dir / "prompts.md").read_text(encoding="utf-8")

        self.assertIn("**主要原因**", content)
        self.assertIn("should_initiate must be boolean", content)
        self.assertIn("### Planner Raw Output", content)
        self.assertIn('"should_initiate": "yes"', content)


if __name__ == "__main__":
    unittest.main()
