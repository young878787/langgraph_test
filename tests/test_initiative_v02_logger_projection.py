from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent import logger


class InitiativeV02LoggerProjectionTests(unittest.TestCase):
    def _render(self, trace: dict) -> str:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            with patch.object(logger, "LOG_DIR", log_dir), patch.object(
                logger, "ERROR_LOG", log_dir / "error.log"
            ), patch.object(logger, "PROMPT_MD", log_dir / "prompts.md"), patch.object(
                logger, "MEMORY_MD", log_dir / "memory.md"
            ):
                logger.init_logs()
                logger.log_initiative_trace("run-live", "l0_01", trace)
                logger.log_initiative_summary([{
                    "scenario_id": "l0_01",
                    "status": trace["result"],
                    "trace": trace,
                }])
                return (log_dir / "prompts.md").read_text(encoding="utf-8")

    def test_projects_live_attempts_versions_and_domain_audits(self) -> None:
        content = self._render({
            "result": "PASS",
            "mode": "LIVE_API",
            "scenario": {"title": "live trace"},
            "gates": [{"name": "oracle", "ok": True, "summary": "matched"}],
            "steps": [{
                "step_index": 1,
                "logical_time": "2026-07-13T10:05:00+08:00",
                "trigger": "DUE_EVALUATION",
                "status_before": "DUE",
                "event_version_before": 2,
                "action": "SEND_NOW",
                "status_after": "COMPLETED",
                "event_version_after": 4,
                "model_decision": {"parsed_action": "SEND_NOW"},
                "provider_attempts": [{
                    "attempt": 1,
                    "provider": "GoogleAIStudioProvider",
                    "model": "gemini-test",
                    "prompt_hash": "sha256:abc",
                    "raw_output": '{"action":"SEND_NOW"}',
                    "validation_errors": ["first-pass warning"],
                }],
                "decision_record": {
                    "decision_id": "decision-1",
                    "event_version": 3,
                },
                "delivery_status": "DELIVERED",
                "delivery_audit": {
                    "idempotency_key": "idem-1",
                    "content_hash": "content-1",
                },
            }],
            "cleanup_snapshot": {
                "pending_wakeup_count": 0,
                "presence_subscription_count": 0,
                "active_lease_count": 0,
                "worker_task_count": 0,
            },
        })

        self.assertIn("**Mode**: `LIVE_API`", content)
        self.assertIn("`GoogleAIStudioProvider` / `gemini-test`", content)
        self.assertIn("| DUE | 2 | SEND_NOW", content)
        self.assertIn("| COMPLETED | 4 | decision-1 | DELIVERED | idem-1 / content-1 |", content)
        self.assertIn("| 1 | 1 | GoogleAIStudioProvider | gemini-test | sha256:abc | first-pass warning |", content)
        self.assertIn('"raw_output"', content)
        self.assertIn('"raw_output": "{\\"action\\":\\"SEND_NOW\\"}"', content)
        self.assertIn('"decision_id": "decision-1"', content)
        self.assertIn('"idempotency_key": "idem-1"', content)
        self.assertIn('"pending_wakeup_count": 0', content)

    def test_error_without_explicit_gate_gets_error_gate(self) -> None:
        content = self._render({
            "result": "ERROR",
            "mode": "LIVE_API",
            "scenario": {"title": "quota error"},
            "errors": ["429 RESOURCE_EXHAUSTED"],
            "failure": {"primary_reason": "provider_error"},
            "cleanup_snapshot": {"worker_task_count": 0},
        })

        self.assertIn("| FAIL | runner_result | 429 RESOURCE_EXHAUSTED |", content)
        self.assertIn("**主要原因**：`provider_error`", content)
        self.assertIn("💥 **ERROR**", content)
        self.assertNotIn("未發現錯誤或失敗 gate", content)
        self.assertNotIn("所有 gate 通過", content)

    def test_pass_without_gates_is_not_described_as_verified(self) -> None:
        content = self._render({
            "result": "PASS",
            "scenario": {"title": "ungated"},
            "cleanup_snapshot": {},
        })

        self.assertIn("未提供可驗證 gate", content)
        self.assertIn("未提供 gate，無法獨立驗證", content)
        self.assertNotIn("所有 gate 通過", content)


if __name__ == "__main__":
    unittest.main()
