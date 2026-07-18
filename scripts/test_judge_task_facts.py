from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent.config import AgentConfig
from agent.llm.judging import build_judge_prompts
from agent.nodes.judge import _run_smart_fallback, judge_input
from agent.nodes.emotion import should_apply_emotion_event
from agent.task_status import (
    build_task_status,
    format_task_status_for_prompt,
    is_fake_praise_for_unproduced_task,
)


VALID_NORMAL_JUDGE = """{
  "category": "normal",
  "event_type": "question",
  "intensity": 0.3,
  "risk": 0.0,
  "relationship_signal": "neutral",
  "ambiguous": false,
  "sarcasm_possible": false,
  "requires_action": false,
  "target": "assistant",
  "state_delta_suggestion": {}
}"""


class _SequenceProvider:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls = 0

    def generate_json(self, *args, **kwargs) -> str:
        result = self.outputs[self.calls]
        self.calls += 1
        return result


class TaskFactTests(unittest.TestCase):
    def test_stance_does_not_claim_artifact_was_produced(self) -> None:
        base = {"category": "task_request", "user_input": "幫我整理資料", "response": "處理好了"}
        helpful = build_task_status({**base, "action_stance": "sudden_competence"}, 3)
        dismissive = build_task_status({**base, "action_stance": "dismissive"}, 3)

        self.assertEqual(helpful["produced_artifact"], "unknown")
        self.assertEqual(dismissive["produced_artifact"], "unknown")
        self.assertEqual(helpful["evidence_source"], "unobserved")

    def test_explicit_response_observation_has_provenance(self) -> None:
        status = build_task_status(
            {
                "category": "task_request",
                "user_input": "幫我整理資料",
                "response": "已整理",
                "artifact_observation": {
                    "produced_artifact": True,
                    "evidence_source": "response_artifact_validator",
                },
            },
            4,
        )
        self.assertIs(status["produced_artifact"], True)
        self.assertEqual(status["outcome"], "completed")
        self.assertEqual(status["evidence_source"], "response_artifact_validator")

    def test_unknown_is_not_formatted_as_no_artifact(self) -> None:
        prompt = format_task_status_for_prompt({"produced_artifact": "unknown"})
        self.assertIn("是否產出未知", prompt)
        self.assertNotIn("沒有產出成果", prompt)

    def test_premise_conflict_requires_strong_fact_and_reference(self) -> None:
        status = {"outcome": "rejected", "produced_artifact": False, "requested_artifact": "poem"}
        self.assertTrue(
            is_fake_praise_for_unproduced_task(
                {"last_task_status": status, "user_input": "你剛寫的詩真的很好"}
            )
        )
        self.assertFalse(
            is_fake_praise_for_unproduced_task(
                {"last_task_status": status, "user_input": "這首歌很好聽"}
            )
        )
        self.assertFalse(
            is_fake_praise_for_unproduced_task(
                {
                    "last_task_status": {**status, "produced_artifact": "unknown"},
                    "user_input": "你剛寫的詩真的很好",
                }
            )
        )


class JudgeContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AgentConfig()

    def test_normal_prompt_has_no_keyword_evidence(self) -> None:
        system, user = build_judge_prompts(
            {"user_input": "你很棒", "keyword_signals": [{"category": "praise", "trigger": "棒"}]}
        )
        combined = system + user
        self.assertNotIn("Keyword evidence", combined)
        self.assertNotIn("Keyword confidence", combined)

    def test_successful_llm_appraisal_is_not_reclassified(self) -> None:
        provider = _SequenceProvider([VALID_NORMAL_JUDGE])
        state = {
            "user_input": "你剛寫的詩很好",
            "last_task_status": {
                "outcome": "rejected",
                "produced_artifact": False,
                "requested_artifact": "poem",
            },
        }
        with patch("agent.nodes.judge.get_provider", return_value=provider):
            result = judge_input(state, self.config)

        self.assertEqual(result["category"], "normal")
        self.assertEqual(result["event_analysis"]["event_type"], "question")
        self.assertTrue(result["event_analysis"]["premise_conflict_candidate"])

    def test_two_invalid_calls_keep_low_confidence_rule_fallback(self) -> None:
        provider = _SequenceProvider(["not json", "still not json"])
        with patch("agent.nodes.judge.get_provider", return_value=provider):
            result = judge_input({"user_input": "你好"}, self.config)

        event = result["event_analysis"]
        self.assertEqual(provider.calls, 2)
        self.assertEqual(result["judge_source"], "rule")
        self.assertEqual(event["judge_source"], "rule")
        self.assertEqual(event["appraisal_confidence"], "low")
        self.assertTrue(event["fallback_reason"])
        self.assertEqual(event["relationship_signal"], "neutral")
        self.assertEqual(event["state_delta_suggestion"], {})
        self.assertLessEqual(event["intensity"], 0.1)

    def test_rule_premise_correction_only_for_strong_reference(self) -> None:
        status = {"outcome": "rejected", "produced_artifact": False, "requested_artifact": "poem"}
        strong = _run_smart_fallback(
            {"user_input": "你剛寫的詩很好", "last_task_status": status}, self.config
        )
        weak = _run_smart_fallback(
            {"user_input": "這首歌很好聽", "last_task_status": status}, self.config
        )
        self.assertEqual(strong["category"], "questioning")
        self.assertTrue(strong["fake_praise"])
        self.assertFalse(weak["fake_praise"])

    def test_low_confidence_rule_appraisal_is_decay_only(self) -> None:
        fallback = _run_smart_fallback({"user_input": "你很好"}, self.config)
        self.assertFalse(should_apply_emotion_event(fallback))


if __name__ == "__main__":
    unittest.main()
