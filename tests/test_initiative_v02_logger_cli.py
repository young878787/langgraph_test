from __future__ import annotations

import asyncio
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
import sys
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent import logger


SCRIPT = ROOT / "scripts" / "replay_initiative_v02.py"
SPEC = importlib.util.spec_from_file_location("replay_initiative_v02", SCRIPT)
assert SPEC and SPEC.loader
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class InitiativeV02LoggerTests(unittest.TestCase):
    def test_structured_trace_projects_steps_cleanup_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            with patch.object(logger, "LOG_DIR", log_dir), patch.object(
                logger, "ERROR_LOG", log_dir / "error.log"
            ), patch.object(logger, "PROMPT_MD", log_dir / "prompts.md"), patch.object(
                logger, "MEMORY_MD", log_dir / "memory.md"
            ):
                logger.init_logs()
                trace = {
                    "result": "PASS",
                    "scenario": {"title": "五分鐘後回來", "category": "L0"},
                    "steps": [{
                        "step_index": 1,
                        "logical_time": "2026-07-13T10:05:00+08:00",
                        "trigger": {"type": "DUE_EVALUATION"},
                        "event_before": {"status": "DUE", "version": 2},
                        "model_decision": {"parsed_action": "SEND_NOW"},
                        "system_decision": {"reason_codes": ["promise_due"]},
                        "event_after": {"status": "COMPLETED", "version": 4},
                        "delivery": {"status": "DELIVERED"},
                        "gates": [{"name": "transition", "ok": True}],
                    }],
                    "cleanup_snapshot": {"event_status": "COMPLETED", "delivery_count": 1},
                    "hard_constraints": [{
                        "name": "exactly_once", "expected": 1, "actual": 1,
                        "ok": True, "evidence": "receipt-1",
                    }],
                }
                logger.log_initiative_trace("run", "l0_01", trace)
                logger.log_initiative_summary([{
                    "scenario_id": "l0_01", "status": "PASS", "trace": trace,
                }])
                content = (log_dir / "prompts.md").read_text(encoding="utf-8")

        self.assertIn("### 步驟判斷表", content)
        self.assertIn("| 1 | 2026-07-13T10:05:00+08:00 | DUE_EVALUATION | DUE | 2 | SEND_NOW", content)
        self.assertIn("### 最終資源快照", content)
        self.assertIn("| exactly_once | 1 | 1 | PASS | receipt-1 |", content)
        self.assertIn("| 第一主要動作 | 最終狀態 | Delivery | 失敗 Gate |", content)
        self.assertIn("| `l0_01` | SEND_NOW | COMPLETED | 1 |", content)


class InitiativeV02CliTests(unittest.TestCase):
    def test_mapping_adapter_accepts_dataclass(self) -> None:
        @dataclass
        class Result:
            value: int

        self.assertEqual(cli.to_mapping(Result(3)), {"value": 3})

    def test_mapping_adapter_prefers_structured_adapter_over_asdict(self) -> None:
        @dataclass
        class Result:
            value: int

            def to_mapping(self):
                return {"structured": self.value}

        self.assertEqual(cli.to_mapping(Result(3)), {"structured": 3})

    def test_invoke_runner_reports_missing_adapter(self) -> None:
        class Module:
            class ScenarioRunnerV02:
                pass

        with patch.object(cli.importlib, "import_module", return_value=Module()):
            with self.assertRaisesRegex(RuntimeError, "run_scenarios"):
                asyncio.run(cli.invoke_runner((), live_api=False, repeat=1, seed=None))

    def test_invoke_runner_awaits_batch_hook(self) -> None:
        captured = {}

        class Module:
            @staticmethod
            async def run_scenarios(fixtures, **kwargs):
                captured.update(kwargs)
                return [{"fixtures": len(fixtures), "live": kwargs["live_api"]}]

        with patch.object(cli.importlib, "import_module", return_value=Module()):
            result = asyncio.run(cli.invoke_runner((object(),), live_api=True, repeat=1, seed=7))
        self.assertEqual(result, [{"fixtures": 1, "live": True}])
        self.assertEqual(captured, {"live_api": True, "repeat": 1, "seed": 7})

    def test_live_runner_model_payload_excludes_oracle(self) -> None:
        fixture = cli.load_scenarios(cli.FIXTURE_PATH)[0]
        captured = {}

        class Module:
            @staticmethod
            async def run_scenarios(fixtures, **kwargs):
                captured["live_api"] = kwargs["live_api"]
                captured["model_payload"] = fixtures[0].model.to_payload()
                return []

        with patch.object(cli.importlib, "import_module", return_value=Module()):
            asyncio.run(cli.invoke_runner((fixture,), live_api=True, repeat=1, seed=None))

        encoded = json.dumps(captured["model_payload"], ensure_ascii=False).casefold()
        self.assertTrue(captured["live_api"])
        self.assertNotIn('"oracle"', encoded)
        self.assertNotIn('"expected_', encoded)
        self.assertNotIn('"hard_constraints"', encoded)
        self.assertNotIn('"soft_preferences"', encoded)

    def test_async_main_prints_live_mode_and_forwards_flag(self) -> None:
        fixture = cli.load_scenarios(cli.FIXTURE_PATH)[0]
        expected = fixture.oracle.expected_final
        result = {
            "event": {"status": expected.event_status},
            "event_count": expected.event_count,
            "decision_count": expected.decision_count,
            "delivery_count": expected.delivery_count,
            "transport_message_count": expected.transport_message_count,
            "actions": [fixture.oracle.expected_action],
            "traces": [],
            "cleanup": {
                "pending_wakeup_count": expected.pending_wakeup_count,
                "presence_subscription_count": expected.presence_subscription_count,
                "active_lease_count": expected.active_lease_count,
                "worker_task_count": expected.worker_task_count,
            },
        }

        async def fake_invoke(fixtures, **kwargs):
            self.assertEqual(fixtures, (fixture,))
            self.assertTrue(kwargs["live_api"])
            return [result]

        args = cli.parse_args([
            "--scenario", fixture.model.scenario_id,
            "--live-api",
            "--fixture", str(cli.FIXTURE_PATH),
        ])
        output = io.StringIO()
        with patch.object(cli, "load_scenarios", return_value=(fixture,)), patch.object(
            cli, "invoke_runner", side_effect=fake_invoke
        ) as invoke, patch.object(cli, "init_logs"), patch.object(
            cli, "log_initiative_trace"
        ), patch.object(cli, "log_initiative_summary"), redirect_stdout(output):
            exit_code = asyncio.run(cli.async_main(args))

        self.assertEqual(exit_code, 0)
        self.assertEqual(invoke.await_count, 1)
        self.assertIn("Replay mode: LIVE_API", output.getvalue())
        self.assertIn("real AI provider via AgentConfig / LLM_BACKEND", output.getvalue())

    def test_async_main_prints_deterministic_mode(self) -> None:
        fixture = cli.load_scenarios(cli.FIXTURE_PATH)[0]
        args = cli.parse_args(["--scenario", fixture.model.scenario_id])

        async def fail_before_result(fixtures, **kwargs):
            self.assertFalse(kwargs["live_api"])
            raise RuntimeError("stop after mode assertion")

        output = io.StringIO()
        with patch.object(cli, "load_scenarios", return_value=(fixture,)), patch.object(
            cli, "invoke_runner", side_effect=fail_before_result
        ), patch.object(cli, "init_logs"), patch.object(cli, "log_error") as error_log, patch.object(
            cli, "log_initiative_trace"
        ), patch.object(cli, "log_initiative_summary"), redirect_stdout(output):
            exit_code = asyncio.run(cli.async_main(args))

        self.assertEqual(exit_code, 2)
        error_log.assert_called_once()
        self.assertIn("Replay mode: DETERMINISTIC", output.getvalue())
        self.assertIn("no AI API call", output.getvalue())

    def test_async_main_initializes_before_runner_and_preserves_prior_results_on_error(self) -> None:
        fixtures = cli.load_scenarios(cli.FIXTURE_PATH)[:2]
        call_order = []

        def initialized():
            call_order.append("init")

        async def fake_invoke(selected, **kwargs):
            fixture = selected[0]
            call_order.append(f"run:{fixture.model.scenario_id}")
            if fixture is fixtures[1]:
                raise RuntimeError("provider quota exhausted")
            expected = fixture.oracle.expected_final
            return [{
                "event_status": expected.event_status,
                "event_count": expected.event_count,
                "decision_count": expected.decision_count,
                "delivery_count": expected.delivery_count,
                "transport_message_count": expected.transport_message_count,
                "actions": [fixture.oracle.expected_action],
                "traces": [],
                "cleanup_snapshot": {
                    "pending_wakeup_count": expected.pending_wakeup_count,
                    "presence_subscription_count": expected.presence_subscription_count,
                    "active_lease_count": expected.active_lease_count,
                    "worker_task_count": expected.worker_task_count,
                },
            }]

        args = cli.parse_args(["--all", "--live-api", "--seed", "41"])
        traces = []
        summaries = []
        with patch.object(cli, "load_scenarios", return_value=fixtures), patch.object(
            cli, "invoke_runner", side_effect=fake_invoke
        ), patch.object(cli, "init_logs", side_effect=initialized), patch.object(
            cli, "log_error"
        ) as error_log, patch.object(
            cli, "log_initiative_trace", side_effect=lambda *args: traces.append(args)
        ), patch.object(
            cli, "log_initiative_summary", side_effect=lambda payloads: summaries.append(list(payloads))
        ):
            exit_code = asyncio.run(cli.async_main(args))

        self.assertEqual(exit_code, 2)
        self.assertEqual(call_order, [
            "init", f"run:{fixtures[0].model.scenario_id}", f"run:{fixtures[1].model.scenario_id}",
        ])
        self.assertEqual([item[2]["result"] for item in traces], ["PASS", "ERROR"])
        self.assertEqual([len(items) for items in summaries], [1, 2])
        self.assertEqual(summaries[-1][0]["status"], "PASS")
        self.assertEqual(summaries[-1][1]["status"], "ERROR")
        self.assertEqual(summaries[-1][1]["trace"]["scenario"]["run_seed"], 41)
        self.assertEqual(summaries[-1][1]["trace"]["scenario"]["mode"], "LIVE_API")
        error_log.assert_called_once()

    def test_error_payload_preserves_partial_result_steps_cleanup_and_provider(self) -> None:
        fixture = cli.load_scenarios(cli.FIXTURE_PATH)[0]

        @dataclass
        class Partial:
            ignored: bool = True

            def to_mapping(self):
                return {
                    "event_status": "DUE",
                    "delivery_count": 0,
                    "traces": [{
                        "step_id": "step-1",
                        "provider_attempts": [{
                            "attempt": 1,
                            "provider": "GoogleAIStudioProvider",
                            "prompt_hash": "sha256:abc",
                            "validation_error": "provider_error: quota",
                        }],
                    }],
                    "cleanup_snapshot": {"worker_task_count": 0},
                }

        error = RuntimeError("quota")
        error.partial_result = Partial()
        payload = cli.error_payload(error, fixture, 2, run_seed=8, live_api=True)

        self.assertEqual(payload["status"], "ERROR")
        self.assertEqual(payload["trace"]["steps"][0]["step_id"], "step-1")
        self.assertEqual(payload["trace"]["cleanup_snapshot"], {"worker_task_count": 0})
        self.assertEqual(
            payload["trace"]["scenario"]["provider_backend"], "GoogleAIStudioProvider"
        )
        self.assertEqual(payload["trace"]["scenario"]["run_seed"], 8)


if __name__ == "__main__":
    unittest.main()
