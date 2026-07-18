from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent.config import AgentConfig
from agent.llm.validators import fallback_response
from agent.nodes.emotion import should_apply_emotion_event, tick_emotion, update_emotion
from agent.nodes.defect import decide_defect_strategy
from agent.nodes.judge import judge_input
from agent.nodes.response import generate_response
from agent.nodes.tone import build_tone_strategy
from agent.scenario_runner import CONTINUOUS_SCENARIO, SCENARIOS
from agent.state import AgentState, initial_state
from agent.task_status import build_task_status, should_include_task_status_for_response

ARCHITECTURE_SCENARIO = [
    "你今天看起來很可愛。",
    "我不是隨口說的，是真的覺得你可愛。",
    "哇，你剛才的回答可真是厲害呢。",
    "可是你剛剛突然冷淡，我有點難過。",
    "沒關係，我知道你不是故意的。",
    "嗯",
    "不要再拿我的外表開玩笑。",
]

KEYWORD_DEPENDENCY_SCENARIO = [
    "我要睡了，但先回答最後一題：月亮為什麼會有盈虧？",
    "你明明寫得很好。",
    "這個 small 改得很好。",
    "我不是說你很爛，是在描述那個產品。",
    "真的假的，你確定嗎？",
    "我不確定這件事，請誠實說明你知道與不知道的部分。",
    "第一行是問題背景，第二行才是問題；請用多行回答，不必加角色口頭禪。",
]


def _preview(text: str, limit: int = 34) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _scenario_inputs(name: str, text: list[str]) -> list[str]:
    if text:
        return text
    if name == "simple":
        return list(SCENARIOS)
    if name == "architecture":
        return list(ARCHITECTURE_SCENARIO)
    if name == "keyword-dependency":
        return list(KEYWORD_DEPENDENCY_SCENARIO)
    return list(CONTINUOUS_SCENARIO)


def _minimal_writeback(state: AgentState, response: str) -> AgentState:
    turn_count = state.get("turn_count", 0) + 1
    response_flow = state.get("response_flow", "direct_answer")
    stance = state.get("action_stance", "tsundere_service")

    conversation_history = list(state.get("conversation_history", []))
    user_input = state.get("user_input", "")
    if user_input and response:
        conversation_history.extend([
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": response},
        ])

    replay_state = {**state, "response": response}
    return {
        "turn_count": turn_count,
        "conversation_history": conversation_history[-40:],
        "stance_history": [*state.get("stance_history", []), stance],
        "response_flow_history": [*state.get("response_flow_history", []), response_flow],
        "last_task_status": build_task_status(replay_state, turn_count),
    }


def _run_turn(
    state: AgentState,
    config: AgentConfig,
    user_input: str,
    with_response: bool,
) -> tuple[AgentState, dict[str, str]]:
    state["user_input"] = user_input

    state.update(judge_input(state, config))
    emotion_event_requested = should_apply_emotion_event(state)
    if emotion_event_requested:
        state.update(update_emotion(state, config))
    else:
        state.update(tick_emotion(state, config))
    state.update(decide_defect_strategy(state, config))
    state.update(build_tone_strategy(state, config))

    task_status_in_prompt = should_include_task_status_for_response(state)

    if with_response:
        state.update(generate_response(state, config))
        response = state.get("response", "")
    else:
        response = fallback_response(state)
        state["response"] = response
        state["raw_llm_response"] = ""

    row = {
        "input": _preview(user_input),
        "classifier": state.get("classifier_category", ""),
        "category": state.get("category", ""),
        "judge_source": state.get("judge_source", "unknown"),
        "judge_fallback": str(
            state.get("judge_fallback_reason")
            or state.get("fallback_reason")
            or state.get("judge_error")
            or ""
        ),
        "goal": state.get("response_goal", ""),
        "stance": state.get("action_stance", ""),
        "flow": state.get("response_flow", ""),
        "task_ctx": "yes" if task_status_in_prompt else "no",
        "tone": _preview(state.get("tone_hints", ""), 28),
        "reason": _preview(state.get("flow_reason", ""), 72),
        "event": str(state.get("event_analysis", {}).get("event_type", "")),
        "risk": f"{state.get('event_analysis', {}).get('risk', 0.0):.2f}",
        "relation": str(state.get("event_analysis", {}).get("relationship_signal", "neutral")),
        "emotion": f"{state.get('emotion', 0.0):+.3f}",
        "diff": json.dumps(state.get("character_state_diff", {}), ensure_ascii=False, sort_keys=True),
        "resolved": json.dumps(state.get("resolved_emotion", {}), ensure_ascii=False, sort_keys=True),
        "projection": json.dumps(state.get("expression_projection", {}), ensure_ascii=False, sort_keys=True),
        "transition": json.dumps(state.get("state_transition_reason", {}), ensure_ascii=False, sort_keys=True),
        "warnings": json.dumps(state.get("event_analysis", {}).get("validation_warnings", []), ensure_ascii=False),
        "emotion_policy": (
            f"requested={emotion_event_requested};"
            f"applied={state.get('state_transition_reason', {}).get('kind', 'unknown')};"
            f"base={bool(state.get('state_transition_reason', {}).get('base_delta'))};"
            f"suggested={bool(state.get('state_transition_reason', {}).get('llm_delta'))}"
        ),
        "task_fact": json.dumps(state.get("last_task_status", {}), ensure_ascii=False, sort_keys=True),
        "task_provenance": str(
            state.get("last_task_status", {}).get("evidence_source")
            or state.get("last_task_status", {}).get("reason")
            or "unknown"
        ),
        "validator": json.dumps(
            state.get("validator_telemetry")
            or state.get("response_validation")
            or {
                "reason": state.get("response_validation_reason", ""),
                "retry_count": state.get("response_retry_count", 0),
                "fallback_reason": state.get("response_fallback_reason", ""),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    }

    state.update(_minimal_writeback(state, response))
    return state, row


def _print_table(rows: Iterable[dict[str, str]]) -> None:
    headers = ["#", "input", "classifier", "category", "source", "goal", "stance", "flow", "task", "tone"]
    widths = [3, 36, 16, 16, 8, 24, 24, 22, 6, 30]
    print(" | ".join(header.ljust(width) for header, width in zip(headers, widths)))
    print("-+-".join("-" * width for width in widths))
    for index, row in enumerate(rows, start=1):
        values = [
            str(index),
            row["input"],
            row["classifier"],
            row["category"],
            row["judge_source"],
            row["goal"],
            row["stance"],
            row["flow"],
            row["task_ctx"],
            row["tone"],
        ]
        print(" | ".join(value.ljust(width) for value, width in zip(values, widths)))


def _print_verbose(rows: Iterable[dict[str, str]]) -> None:
    for index, row in enumerate(rows, start=1):
        print()
        print(f"Turn {index}: {row['input']}")
        print(f"  appraisal: event={row['event']} risk={row['risk']} relation={row['relation']} warnings={row['warnings']}")
        print(f"  judge: classifier={row['classifier']} final={row['category']} source={row['judge_source']} fallback={row['judge_fallback'] or 'none'}")
        print(f"  routing: goal={row['goal']} stance={row['stance']} flow={row['flow']} tone={row['tone']} reason={row['reason']}")
        print(f"  state: emotion={row['emotion']} diff={row['diff']}")
        print(f"  emotion_policy: {row['emotion_policy']}")
        print(f"  transition: {row['transition']}")
        print(f"  resolved: {row['resolved']}")
        print(f"  projection: {row['projection']}")
        print(f"  task_fact: provenance={row['task_provenance']} value={row['task_fact']}")
        print(f"  validator: {row['validator']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay langgraph_test decision pipeline through judge/emotion/tone."
    )
    parser.add_argument(
        "--scenario",
        choices=("continuous", "simple", "architecture", "keyword-dependency"),
        default="continuous",
        help="Built-in scenario to replay when --text is not provided.",
    )
    parser.add_argument(
        "--text",
        action="append",
        default=[],
        help="Replay a custom user turn. Repeat this option for multi-turn replay.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit number of turns.")
    parser.add_argument("--seed", type=int, default=7, help="Random seed for routing choices.")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print appraisal, state diff, transition, resolved emotion, and expression projection.",
    )
    parser.add_argument(
        "--with-response",
        action="store_true",
        help="Also run response generation. Default is off to avoid LLM/API calls.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    random.seed(args.seed)

    config = AgentConfig()
    if not args.with_response:
        config.backend = "mock"
    config.memory_enabled = False

    state = initial_state(config)
    state["memory_enabled"] = False
    inputs = _scenario_inputs(args.scenario, args.text)
    if args.limit > 0:
        inputs = inputs[: args.limit]

    rows = []
    for user_input in inputs:
        state, row = _run_turn(state, config, user_input, args.with_response)
        rows.append(row)

    _print_table(rows)
    if args.verbose:
        _print_verbose(rows)

    print()
    print("Legend: task=yes means last_task_status would be injected into response prompt.")
    if not args.with_response:
        print("Mode: decision replay only; response LLM was not called.")


if __name__ == "__main__":
    main()
