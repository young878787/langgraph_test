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
                    "flow_result": trace.get("flow_result", trace.get("result")),
                    "human_review": trace.get("human_review", "PENDING"),
                    "trace": trace,
                }])
                return (log_dir / "prompts.md").read_text(encoding="utf-8")

    def test_projects_live_attempts_versions_and_domain_audits(self) -> None:
        content = self._render({
            "flow_result": "PASS",
            "human_review": "PENDING",
            "mode": "LIVE_MODEL_E2E_VIRTUAL_IO",
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
                    "call_id": "run:l0_01:reappraisal:1",
                    "stage": "reappraisal",
                    "attempt": 1,
                    "provider": "GoogleAIStudioProvider",
                    "model": "gemini-test",
                    "elapsed_ms": 125,
                    "validation_status": "accepted",
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

        self.assertIn("**Mode**: `LIVE_MODEL_E2E_VIRTUAL_IO`", content)
        self.assertIn("**Flow result**: `PASS`", content)
        self.assertIn("**Human review**: `PENDING`", content)
        self.assertIn("`GoogleAIStudioProvider` / `gemini-test`", content)
        self.assertIn("| DUE | 2 | SEND_NOW", content)
        self.assertIn("| COMPLETED | 4 | decision-1 | DELIVERED | idem-1 / content-1 |", content)
        self.assertIn(
            "| run:l0_01:reappraisal:1 | reappraisal | 1 | 1 | "
            "GoogleAIStudioProvider | gemini-test | 125 | accepted | sha256:abc | first-pass warning |",
            content,
        )
        self.assertIn('"raw_output"', content)
        self.assertIn('"raw_output": "{\\"action\\":\\"SEND_NOW\\"}"', content)
        self.assertIn('"decision_id": "decision-1"', content)
        self.assertIn('"idempotency_key": "idem-1"', content)
        self.assertIn('"pending_wakeup_count": 0', content)
        self.assertIn("展開 debug 細節：Gate、Audit、Provider attempts 與 raw output", content)
        self.assertNotIn("### Prompt 指紋", content)
        self.assertGreater(
            content.index("### AI Call Ledger"),
            content.index("展開 debug 細節"),
        )

    def test_error_without_explicit_gate_gets_error_gate(self) -> None:
        content = self._render({
            "flow_result": "ERROR",
            "human_review": "PENDING",
            "mode": "LIVE_MODEL_E2E_VIRTUAL_IO",
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

    def test_projects_top_level_live_call_ledger_and_ai_decision(self) -> None:
        content = self._render({
            "flow_result": "PASS",
            "human_review": "PENDING",
            "scenario": {"title": "ledger trace"},
            "gates": [{"name": "coverage", "ok": True, "summary": "complete"}],
            "call_ledger": [{
                "call_id": "run:scan:1",
                "stage": "candidate_scan",
                "attempt": 1,
                "provider": "GoogleAIStudioProvider",
                "model": "gemini-test",
                "elapsed_ms": 42,
                "validation_status": "accepted",
                "validation_errors": [],
                "prompt_hash": "sha256:scan",
                "raw_response": (
                    '{"decision_type":"candidate_scan","short_rationale":"有明確承諾",'
                    '"evidence_refs":["turn:u1"]}'
                ),
            }],
        })

        self.assertIn("| run:scan:1 | candidate_scan |", content)
        self.assertIn("有明確承諾", content)
        self.assertIn("turn:u1", content)
        self.assertIn("sha256:scan", content)

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
