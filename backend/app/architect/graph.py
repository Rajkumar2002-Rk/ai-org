"""LangGraph wiring for the Architect agent.

A single-node graph today (design), but structured as a graph so future
steps (e.g. validation, cost review) can be added as nodes without
rewriting the caller.
"""
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.architect import builder


class ArchState(TypedDict, total=False):
    summary: dict[str, Any]
    blueprint: dict[str, Any]


async def _design(state: ArchState) -> ArchState:
    state["blueprint"] = await builder.build_blueprint(state["summary"])
    return state


_graph = StateGraph(ArchState)
_graph.add_node("design", _design)
_graph.add_edge(START, "design")
_graph.add_edge("design", END)
_compiled = _graph.compile()


async def run(summary: dict) -> dict:
    """Run the Architect and return the finished blueprint."""
    result = await _compiled.ainvoke({"summary": summary})
    return result["blueprint"]
