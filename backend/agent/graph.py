from langgraph.graph import END, StateGraph

from .nodes import reason_node, should_continue, tool_node
from .state import AgentState


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("reason", reason_node)
    graph.add_node("tool", tool_node)
    graph.set_entry_point("reason")
    graph.add_conditional_edges(
        "reason",
        should_continue,
        {"continue": "tool", "end": END},
    )
    graph.add_edge("tool", "reason")
    return graph.compile()
