from __future__ import annotations

import sys
from pathlib import Path
import types as python_types
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if "agent" not in sys.modules:
    package = python_types.ModuleType("agent")
    package.__path__ = [str(SRC / "agent")]
    sys.modules["agent"] = package

from agent.llm.providers import GoogleAIStudioProvider


class GoogleAIStudioProviderTests(unittest.TestCase):
    def test_generate_json_surfaces_non_retryable_provider_error(self) -> None:
        provider = GoogleAIStudioProvider.__new__(GoogleAIStudioProvider)
        provider.model = "test-model"
        provider.client = Mock()
        provider.client.models.generate_content.side_effect = ValueError("invalid request")

        with self.assertRaisesRegex(
            RuntimeError,
            "Google AI Studio JSON request failed for model test-model: invalid request",
        ):
            provider.generate_json("system", "user", 0.1, 128)

        self.assertEqual(provider.client.models.generate_content.call_count, 1)

    def test_generate_json_does_not_disguise_empty_response_as_json(self) -> None:
        provider = GoogleAIStudioProvider.__new__(GoogleAIStudioProvider)
        provider.model = "test-model"

        with patch.object(
            provider, "_generate_json_internal", side_effect=[None, None]
        ) as generate, patch("agent.llm.providers.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "returned an empty response"):
                provider.generate_json("system", "user", 0.1, 128)

        self.assertEqual(generate.call_count, 2)


if __name__ == "__main__":
    unittest.main()
