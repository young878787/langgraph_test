from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent.config import AgentConfig
from agent.state import AgentState, initial_state
from agent.nodes import (
    judge_input,
    should_apply_emotion_event,
    tick_emotion,
    update_emotion,
    build_tone_strategy,
    generate_response,
    writeback,
)


def _should_skip_emotion(state: AgentState) -> str:
    return "emotion" if should_apply_emotion_event(state) else "tone"


def build_graph(config: AgentConfig | None = None, interrupt_before_respond: bool = False):
    config = config or AgentConfig()
    graph = StateGraph(AgentState)

    graph.add_node("judge", lambda state: judge_input(state, config))
    graph.add_node("emotion", lambda state: update_emotion(state, config))
    graph.add_node("emotion_tick", lambda state: tick_emotion(state, config))
    graph.add_node("tone", lambda state: build_tone_strategy(state, config))
    graph.add_node("respond", lambda state: generate_response(state, config))
    graph.add_node("writeback", lambda state: writeback(state, config))

    graph.set_entry_point("judge")

    graph.add_conditional_edges(
        "judge",
        _should_skip_emotion,
        {
            "emotion": "emotion",
            "tone": "emotion_tick",
        },
    )
    graph.add_edge("emotion", "tone")
    graph.add_edge("emotion_tick", "tone")
    graph.add_edge("tone", "respond")
    graph.add_edge("respond", "writeback")
    graph.add_edge("writeback", END)

    compile_kwargs = {}
    if interrupt_before_respond:
        compile_kwargs["interrupt_before"] = ["respond"]

    return graph.compile(**compile_kwargs)


def new_state(config: AgentConfig | None = None) -> AgentState:
    config = config or AgentConfig()
    return initial_state(config)
