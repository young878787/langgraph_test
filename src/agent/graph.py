from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent.config import AgentConfig
from agent.state import AgentState, initial_state
from agent.nodes import (
    judge_input,
    update_emotion,
    build_tone_strategy,
    generate_response,
    writeback,
)


def build_graph(config: AgentConfig | None = None):
    config = config or AgentConfig()
    graph = StateGraph(AgentState)

    graph.add_node("judge", lambda state: judge_input(state, config))
    graph.add_node("emotion", lambda state: update_emotion(state, config))
    graph.add_node("tone", lambda state: build_tone_strategy(state, config))
    graph.add_node("respond", lambda state: generate_response(state, config))
    graph.add_node("writeback", writeback)

    graph.set_entry_point("judge")
    graph.add_edge("judge", "emotion")
    graph.add_edge("emotion", "tone")
    graph.add_edge("tone", "respond")
    graph.add_edge("respond", "writeback")
    graph.add_edge("writeback", END)

    return graph.compile()


def new_state(config: AgentConfig | None = None) -> AgentState:
    config = config or AgentConfig()
    return initial_state(config)
