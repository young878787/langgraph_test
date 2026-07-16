from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent.initiative.decision_contracts import (
    DecisionContractError,
    parse_candidate_consolidation,
    parse_candidate_scan,
    parse_wake_up_reappraisal,
)
from agent.initiative.domain import InitiativeAction


def candidate(candidate_id: str = "candidate:1") -> dict:
    return {
        "candidate_id": candidate_id,
        "event_type": "commitment",
        "summary": "稍後續接目前話題",
        "evidence_refs": ["turn:u1", "turn:a1"],
        "followup_value": "完成已形成的承諾",
        "interruption_risk": "low",
        "trigger": {
            "kind": "time",
            "earliest_offset_minutes": 30,
            "preferred_offset_minutes": 60,
            "expires_offset_minutes": 240,
        },
        "confidence": 0.8,
        "short_rationale": "對話中已有明確未來承諾",
    }


class CandidateDecisionContractTests(unittest.TestCase):
    def test_scan_accepts_exact_contract(self) -> None:
        raw = {
            "schema_version": "initiative.world_event_proposal.v1",
            "decision_type": "candidate_scan",
            "events": [candidate()],
            "no_event_reason": None,
        }
        result = parse_candidate_scan(raw, available_evidence_refs=("turn:u1", "turn:a1"))
        self.assertEqual(result.events[0].candidate_id, "candidate:1")
        self.assertEqual(result.events[0].trigger.preferred_offset_minutes, 60)

    def test_scan_rejects_fence_unknown_key_bool_offset_and_bad_order(self) -> None:
        valid = {
            "schema_version": "initiative.world_event_proposal.v1",
            "decision_type": "candidate_scan",
            "events": [candidate()],
            "no_event_reason": None,
        }
        with self.assertRaises(DecisionContractError):
            parse_candidate_scan(f"```json\n{json.dumps(valid)}\n```", available_evidence_refs=("turn:u1", "turn:a1"))
        invalid = json.loads(json.dumps(valid))
        invalid["extra"] = True
        with self.assertRaises(DecisionContractError):
            parse_candidate_scan(invalid, available_evidence_refs=("turn:u1", "turn:a1"))
        invalid = json.loads(json.dumps(valid))
        invalid["events"][0]["trigger"]["earliest_offset_minutes"] = False
        with self.assertRaises(DecisionContractError):
            parse_candidate_scan(invalid, available_evidence_refs=("turn:u1", "turn:a1"))
        invalid = json.loads(json.dumps(valid))
        invalid["events"][0]["trigger"]["preferred_offset_minutes"] = 240
        with self.assertRaises(DecisionContractError):
            parse_candidate_scan(invalid, available_evidence_refs=("turn:u1", "turn:a1"))

    def test_empty_scan_requires_reason(self) -> None:
        raw = {
            "schema_version": "initiative.world_event_proposal.v1",
            "decision_type": "candidate_scan",
            "events": [],
            "no_event_reason": "目前沒有未完成事項",
        }
        self.assertEqual(
            parse_candidate_scan(raw, available_evidence_refs=()).no_event_reason,
            "目前沒有未完成事項",
        )
        raw["no_event_reason"] = None
        with self.assertRaises(DecisionContractError):
            parse_candidate_scan(raw, available_evidence_refs=())

    def test_consolidation_requires_complete_disjoint_disposition(self) -> None:
        raw = {
            "schema_version": "initiative.world_event_consolidation.v1",
            "decision_type": "candidate_consolidation",
            "accepted_candidate_ids": ["candidate:1"],
            "merged_candidates": [{
                "target_candidate_id": "candidate:1",
                "source_candidate_ids": ["candidate:2"],
            }],
            "rejected_candidates": [{
                "candidate_id": "candidate:3",
                "reason_code": "resolved_in_later_turn",
            }],
            "short_rationale": "保留一項並合併重複候選",
        }
        result = parse_candidate_consolidation(
            raw, known_candidate_ids=("candidate:1", "candidate:2", "candidate:3")
        )
        self.assertEqual(result.merged_candidates[0].source_candidate_ids, ("candidate:2",))
        raw["rejected_candidates"] = []
        with self.assertRaises(DecisionContractError):
            parse_candidate_consolidation(
                raw, known_candidate_ids=("candidate:1", "candidate:2", "candidate:3")
            )


class ReappraisalDecisionContractTests(unittest.TestCase):
    def test_delay_is_relative_and_bound_to_event_version(self) -> None:
        now = datetime(2026, 7, 13, 10, tzinfo=timezone.utc)
        raw = {
            "schema_version": "initiative.reappraisal.v1",
            "decision_type": "wake_up_reappraisal",
            "event_id": "event:1",
            "event_version": 3,
            "action": "DELAY",
            "reason_code": "too_early",
            "evidence_refs": ["turn:u1"],
            "next_evaluation_offset_minutes": 15,
            "short_rationale": "目前介入仍太早",
        }
        result = parse_wake_up_reappraisal(
            raw,
            expected_event_id="event:1",
            expected_event_version=3,
            available_evidence_refs=("turn:u1",),
            logical_now=now,
            expires_at=now + timedelta(hours=1),
        )
        self.assertIs(result.action, InitiativeAction.DELAY)
        self.assertEqual(result.next_evaluation_at, now + timedelta(minutes=15))
        raw["event_version"] = 2
        with self.assertRaises(DecisionContractError):
            parse_wake_up_reappraisal(
                raw, expected_event_id="event:1", expected_event_version=3,
                available_evidence_refs=("turn:u1",), logical_now=now,
                expires_at=now + timedelta(hours=1),
            )

    def test_non_delay_requires_null_offset(self) -> None:
        now = datetime(2026, 7, 13, 10, tzinfo=timezone.utc)
        raw = {
            "schema_version": "initiative.reappraisal.v1",
            "decision_type": "wake_up_reappraisal",
            "event_id": "event:1",
            "event_version": 3,
            "action": "SEND_NOW",
            "reason_code": "still_relevant",
            "evidence_refs": ["turn:u1"],
            "next_evaluation_offset_minutes": 5,
            "short_rationale": "現在適合介入",
        }
        with self.assertRaises(DecisionContractError):
            parse_wake_up_reappraisal(
                raw, expected_event_id="event:1", expected_event_version=3,
                available_evidence_refs=("turn:u1",), logical_now=now,
                expires_at=now + timedelta(hours=1),
            )


if __name__ == "__main__":
    unittest.main()
