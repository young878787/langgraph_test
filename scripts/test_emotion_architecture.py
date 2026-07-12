from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.config import AgentConfig
from agent.graph import build_graph
from agent.llm.judge_validators import parse_judge_output_v2
from agent.llm.prompting import build_prompts
from agent.nodes.emotion import project_activation, tick_emotion, update_emotion
from agent.nodes.tone import build_tone_strategy
from agent.nodes.tone_performance import (
    build_expression_projection,
    resolve_vtuber_emotion,
)
from agent.state import initial_state


class PipelineOrderingTests(unittest.TestCase):
    def test_stance_is_resolved_after_emotion_transition(self) -> None:
        graph = build_graph(AgentConfig()).get_graph()
        edges = {(edge.source, edge.target) for edge in graph.edges}

        self.assertIn(("emotion", "stance"), edges)
        self.assertIn(("emotion_tick", "stance"), edges)
        self.assertIn(("stance", "tone"), edges)
        self.assertNotIn(("emotion", "tone"), edges)
        self.assertNotIn(("emotion_tick", "tone"), edges)


class JudgeValidatorTests(unittest.TestCase):
    def test_canonicalizes_bounded_event_and_drops_unknown_state_keys(self) -> None:
        payload = json.dumps({
            "category": "praise",
            "event_type": "invented_event",
            "intensity": 3,
            "risk": "bad",
            "relationship_signal": "instant_soulmate",
            "target": "assistant",
            "state_delta_suggestion": {"embarrassment": 0.9, "new_dimension": 0.5},
        })

        data, error = parse_judge_output_v2(payload)

        self.assertEqual(error, "")
        self.assertIsNotNone(data)
        assert data is not None
        self.assertEqual(data["event_type"], "praise")
        self.assertEqual(data["intensity"], 1.0)
        self.assertEqual(data["risk"], 0.0)
        self.assertEqual(data["relationship_signal"], "neutral")
        self.assertEqual(data["state_delta_suggestion"], {"embarrassment": 0.2})
        self.assertIn("state_delta_unknown:new_dimension", data["validation_warnings"])


class EmotionReducerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AgentConfig()
        self.config.emotion_jitter = 0.5

    def test_short_tick_decays_without_applying_event_delta(self) -> None:
        state = initial_state(self.config)
        state["category"] = "normal"
        state["user_input"] = "嗯"
        state["character_state"]["embarrassment"] = 0.8
        state["event_analysis"] = {
            "event_type": "praise",
            "intensity": 1.0,
            "state_delta_suggestion": {"embarrassment": 0.2},
        }

        result = tick_emotion(state, self.config)

        self.assertLess(result["character_state"]["embarrassment"], 0.8)
        self.assertEqual(result["state_transition_reason"]["kind"], "decay_only")
        self.assertEqual(result["state_transition_reason"]["base_delta"], {})
        self.assertEqual(result["state_transition_reason"]["llm_delta"], {})

    def test_unknown_state_key_cannot_enter_reducer(self) -> None:
        state = initial_state(self.config)
        state["category"] = "praise"
        state["event_analysis"] = {
            "event_type": "praise",
            "intensity": 1.0,
            "state_delta_suggestion": {"new_dimension": 1.0},
        }

        result = update_emotion(state, self.config)

        self.assertNotIn("new_dimension", result["character_state"])

    def test_scalar_is_projection_of_character_state(self) -> None:
        state = initial_state(self.config)
        state["category"] = "praise"
        state["event_analysis"] = {"event_type": "praise", "intensity": 1.0}

        result = update_emotion(state, self.config)

        expected = project_activation(result["character_state"], self.config.emotion_bounds)
        self.assertEqual(result["emotion"], expected)

    def test_same_activation_can_resolve_to_different_styles(self) -> None:
        shy = initial_state(self.config)["character_state"]
        shy.update({"embarrassment": 0.9, "masking": 0.8, "hostility": 0.0})
        boundary = dict(shy)
        boundary.update({"embarrassment": 0.0, "boundary_pressure": 1.0, "annoyance": 0.8, "dominance": 0.8})
        target_activation = project_activation(shy, self.config.emotion_bounds)
        boundary["energy"] = max(0.0, boundary["energy"] + (target_activation - project_activation(boundary, self.config.emotion_bounds)) / (2.5 * 0.35))

        self.assertAlmostEqual(
            project_activation(shy, self.config.emotion_bounds),
            project_activation(boundary, self.config.emotion_bounds),
            places=6,
        )
        self.assertEqual(resolve_vtuber_emotion(shy)["style"], "tsundere")
        self.assertEqual(resolve_vtuber_emotion(boundary)["style"], "boundary")


class ExpressionProjectionTests(unittest.TestCase):
    def test_projection_merges_into_existing_tone_layer(self) -> None:
        config = AgentConfig()
        state = initial_state(config)
        state.update({
            "category": "praise",
            "action_stance": "tsundere_service",
            "character_state": {
                **state["character_state"],
                "embarrassment": 0.9,
                "masking": 0.8,
            },
        })

        result = build_tone_strategy(state, config)

        self.assertEqual(result["expression_projection"]["style"], "tsundere")
        self.assertIn("外顯方式", result["tone_hints"])
        self.assertIn("說話感覺", result["tone_hints"])
        self.assertNotIn("心裡高興", result["tone_hints"])

    def test_projection_keeps_language_cues_but_drops_inner_and_strategy(self) -> None:
        projection = build_expression_projection(
            {
                "inner": "心裡高興但害羞",
                "outer": "嘴硬、假裝不在乎",
                "tone": "微慌、急躁、掩飾",
                "strategy": "先否認，再間接接受",
                "avoid": ["直接道謝", "長篇大論", "第三項不要投影"],
            },
            {"style": "tsundere", "intensity": 0.9},
        )

        self.assertEqual(projection["display"], "嘴硬、假裝不在乎")
        self.assertEqual(projection["tone"], "微慌、急躁、掩飾")
        self.assertEqual(projection["intensity"], 0.9)
        self.assertNotIn("inner", projection)
        self.assertNotIn("strategy", projection)
        self.assertEqual(projection["avoid"], ["直接道謝", "長篇大論"])

    def test_high_intensity_is_projected_as_bounded_expression_hint(self) -> None:
        config = AgentConfig()
        state = initial_state(config)
        state.update({
            "category": "praise",
            "action_stance": "tsundere_service",
            "character_state": {
                **state["character_state"],
                "boundary_pressure": 1.0,
                "annoyance": 1.0,
                "dominance": 1.0,
                "playfulness": 0.0,
            },
        })

        result = build_tone_strategy(state, config)

        self.assertIn("表現程度：明顯，但不要失控", result["tone_hints"])

    def test_prompt_receives_projected_tone_through_existing_tone_layer(self) -> None:
        config = AgentConfig()
        state = initial_state(config)
        state.update({
            "category": "praise",
            "action_stance": "tsundere_service",
            "character_state": {
                **state["character_state"],
                "embarrassment": 0.9,
                "masking": 0.8,
            },
        })

        result = build_tone_strategy(state, config)
        state.update(result)
        system_prompt, _ = build_prompts(state)

        self.assertIn("【語氣微調】", system_prompt)
        self.assertIn("外顯方式：", system_prompt)
        self.assertIn("說話感覺：", system_prompt)

    def test_close_conversation_goal_suppresses_projection(self) -> None:
        config = AgentConfig()
        state = initial_state(config)
        state.update({
            "category": "farewell",
            "action_stance": "tsundere_service",
            "character_state": {
                **state["character_state"],
                "embarrassment": 0.9,
                "masking": 0.8,
            },
        })

        result = build_tone_strategy(state, config)

        self.assertEqual(result["response_goal"], "close_conversation")
        self.assertNotIn("外顯方式", result["tone_hints"])


if __name__ == "__main__":
    unittest.main()
