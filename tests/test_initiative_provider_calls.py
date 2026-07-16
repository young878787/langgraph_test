from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent.initiative.provider_calls import (
    ProviderCallError,
    ProviderCallLedger,
    ProviderStage,
    ValidationStatus,
)


class FakeProvider:
    model = "test-model"

    def __init__(self, *responses: object) -> None:
        self.responses = iter(responses)

    def generate_json(self, *args: object) -> str:
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return str(value)

    def generate(self, *args: object) -> str:
        return self.generate_json(*args)


class ProviderCallLedgerTests(unittest.TestCase):
    def test_json_call_records_accepted_attempt(self) -> None:
        ledger = ProviderCallLedger("run:1")
        result = ledger.call_json(
            ProviderStage.CANDIDATE_SCAN, FakeProvider('{"ok": true}'),
            "system", "user", 0.1, 100,
            lambda raw: raw if '"ok": true' in raw else (_ for _ in ()).throw(ValueError("bad")),
        )
        self.assertEqual(result.entry.validation_status, ValidationStatus.ACCEPTED)
        self.assertEqual(result.entry.provider, "FakeProvider")
        self.assertEqual(result.entry.model, "test-model")
        self.assertTrue(result.entry.prompt_hash.startswith("sha256:"))

    def test_json_call_allows_exactly_one_correction(self) -> None:
        ledger = ProviderCallLedger("run:1")

        def validator(raw: str) -> str:
            if raw != "valid":
                raise ValueError("invalid contract")
            return raw

        result = ledger.call_json(
            "reappraisal", FakeProvider("invalid", "valid"), "system", "user",
            0.1, 100, validator,
        )
        self.assertEqual([item.attempt for item in result.entries], [1, 2])
        self.assertEqual(result.entries[0].validation_status, ValidationStatus.REJECTED)
        self.assertEqual(result.entries[1].validation_status, ValidationStatus.ACCEPTED)
        self.assertEqual(result.entries[0].call_id, result.entries[1].call_id)

    def test_second_invalid_result_is_error_without_fallback(self) -> None:
        ledger = ProviderCallLedger("run:1")
        with self.assertRaises(ProviderCallError) as caught:
            ledger.call_json(
                "candidate_consolidation", FakeProvider("bad", "still bad"),
                "system", "user", 0.1, 100,
                lambda raw: (_ for _ in ()).throw(ValueError("invalid contract")),
            )
        self.assertEqual(len(caught.exception.entries), 2)
        self.assertTrue(all(item.validation_status is ValidationStatus.REJECTED for item in caught.exception.entries))

    def test_external_tracker_records_real_wrapped_execution(self) -> None:
        ledger = ProviderCallLedger("run:1")
        provider = FakeProvider()
        with ledger.track("dialogue_response", provider) as call:
            raw = "角色真實回覆"
            call.accept(raw)
        self.assertEqual(ledger.entries[0].stage, ProviderStage.DIALOGUE_RESPONSE)
        self.assertEqual(ledger.entries[0].raw_response, raw)
        self.assertEqual(ledger.entries[0].validation_status, ValidationStatus.ACCEPTED)

    def test_external_tracker_records_exception(self) -> None:
        ledger = ProviderCallLedger("run:1")
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with ledger.track("dialogue_response", FakeProvider()):
                raise RuntimeError("boom")
        self.assertEqual(ledger.entries[0].validation_status, ValidationStatus.ERROR)
        self.assertFalse(ledger.entries[0].response_received)


if __name__ == "__main__":
    unittest.main()
