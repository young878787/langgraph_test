from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent.initiative.decision_contracts import (
    CandidateConsolidationDecision,
    CandidateScanDecision,
    InterruptionRisk,
    ProposalTrigger,
    TriggerKind,
    WorldEventCandidate,
    WorldEventType,
)
from agent.initiative.domain import EventStatus, IsolationIdentity
from agent.initiative.event_gate import (
    EventGateContext,
    EventGatePolicy,
    gate_candidate_events,
    persist_accepted_events,
)
from agent.initiative.store import InMemoryInitiativeStore


NOW = datetime(2026, 7, 13, 10, tzinfo=timezone(timedelta(hours=8)))


def identity() -> IsolationIdentity:
    return IsolationIdentity("tenant", "user", "character", "world", "session", "test", "channel", "target")


def candidate(candidate_id: str = "candidate:1", summary: str = "稍後續接") -> WorldEventCandidate:
    return WorldEventCandidate(
        candidate_id, WorldEventType.COMMITMENT, summary, ("turn:u1", "turn:a1"),
        "完成承諾", InterruptionRisk.LOW,
        ProposalTrigger(TriggerKind.TIME, 30, 60, 240), 0.9, "有明確承諾",
    )


def decisions(*items: WorldEventCandidate):
    scan = CandidateScanDecision(
        "initiative.world_event_proposal.v1", "candidate_scan", tuple(items), None
    )
    consolidation = CandidateConsolidationDecision(
        "initiative.world_event_consolidation.v1", "candidate_consolidation",
        tuple(item.candidate_id for item in items), (), (), "全部仍有價值",
    )
    return scan, consolidation


class DeterministicEventGateTests(unittest.TestCase):
    def test_accepted_candidate_builds_timezone_aware_event_from_offsets(self) -> None:
        scan, consolidation = decisions(candidate())
        result = gate_candidate_events(
            scan, consolidation,
            EventGateContext(NOW, identity(), "run:1", ("turn:u1", "turn:a1")),
        )
        self.assertEqual(len(result.accepted), 1)
        event = result.accepted[0].event
        self.assertEqual(event.schedule.earliest_at, NOW + timedelta(minutes=30))
        self.assertEqual(event.schedule.next_evaluation_at, NOW + timedelta(minutes=60))
        self.assertEqual(event.schedule.expires_at, NOW + timedelta(minutes=240))
        self.assertEqual(event.source_turn_ids, ("turn:u1", "turn:a1"))

    def test_gate_rejects_opt_out_sensitive_duplicate_and_caps(self) -> None:
        first = candidate()
        scan, consolidation = decisions(first)
        base = EventGateContext(NOW, identity(), "run:1", ("turn:u1", "turn:a1"))
        active = gate_candidate_events(scan, consolidation, base).accepted[0].event
        cases = (
            replace(base, opted_out_event_types=(WorldEventType.COMMITMENT,)),
            replace(base, sensitive_candidate_ids=(first.candidate_id,)),
            replace(base, active_events=(active,)),
        )
        expected = ("user_opt_out", "sensitive_inference_rejected", "duplicate_active_event")
        for context, reason in zip(cases, expected):
            with self.subTest(reason=reason):
                result = gate_candidate_events(scan, consolidation, context)
                self.assertIn(reason, result.rejected[0].reason_codes)
        result = gate_candidate_events(
            scan, consolidation, base,
            policy=EventGatePolicy(max_events_per_conversation=0),
        )
        self.assertIn("conversation_event_limit", result.rejected[0].reason_codes)

    def test_only_accepted_events_are_persisted_and_activated(self) -> None:
        accepted_candidate = candidate("candidate:1", "保留")
        rejected_candidate = candidate("candidate:2", "不要保留")
        scan = CandidateScanDecision(
            "initiative.world_event_proposal.v1", "candidate_scan",
            (accepted_candidate, rejected_candidate), None,
        )
        consolidation = CandidateConsolidationDecision(
            "initiative.world_event_consolidation.v1", "candidate_consolidation",
            ("candidate:1",), (), (), "只保留一項",
        )
        context = EventGateContext(NOW, identity(), "run:1", ("turn:u1", "turn:a1"))
        result = gate_candidate_events(scan, consolidation, context)
        store = InMemoryInitiativeStore()
        persisted = persist_accepted_events(result, store)
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0].status, EventStatus.SCHEDULED)
        self.assertEqual(len(store.events_for_identity(identity().isolation_key)), 1)


if __name__ == "__main__":
    unittest.main()
