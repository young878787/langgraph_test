from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent.config import AgentConfig  # noqa: E402
from agent.initiative.fixtures import load_fixture  # noqa: E402
from agent.initiative.runner import InitiativeRunner  # noqa: E402


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "initiative" / "delayed_care_after_rest.json"
LIVE_TEST_ENABLED = os.getenv("RUN_LIVE_AI_TESTS", "").lower() in {"1", "true", "yes"}


@unittest.skipUnless(
    LIVE_TEST_ENABLED,
    "set RUN_LIVE_AI_TESTS=1 to allow a real, billable AI API request",
)
class InitiativeLiveApiTests(unittest.TestCase):
    def test_complete_initiative_flow_uses_configured_ai_provider(self) -> None:
        config = AgentConfig(memory_enabled=False)
        backend = (config.backend or "mock").lower()
        if backend == "mock":
            self.skipTest("LLM_BACKEND must select a non-mock provider")

        required_key = (
            "OPENROUTER_API_KEY"
            if backend == "openrouter"
            else "GOOGLE_API_KEY"
            if backend in {"google", "google_ai_studio", "gemini"}
            else ""
        )
        if not required_key:
            self.fail(f"unsupported live AI backend: {config.backend}")
        if not os.getenv(required_key):
            self.skipTest(f"{required_key} is required for backend={config.backend}")

        result = InitiativeRunner(config, live_api=True).run_fixture(
            load_fixture(FIXTURE_PATH, config=config)
        )

        self.assertEqual(
            result.status,
            "PASS",
            msg=f"live initiative flow failed: {result.trace.get('errors')}",
        )
        self.assertTrue(result.initiative_message)
        self.assertNotEqual(result.trace.get("provider"), "MockProvider")
        self.assertIn("planner_raw", result.trace)
        self.assertIn("generator_raw", result.trace)
        self.assertIn("evaluator_raw", result.trace)


if __name__ == "__main__":
    unittest.main()
