"""LangGraph wiring for the Product Intelligence agent."""
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.product_intel import reviewer


class PIState(TypedDict, total=False):
    summary: dict[str, Any]
    review: dict[str, Any]


async def _analyze(state: PIState) -> PIState:
    state["review"] = await reviewer.build_review(state["summary"])
    return state


_graph = StateGraph(PIState)
_graph.add_node("analyze", _analyze)
_graph.add_edge(START, "analyze")
_graph.add_edge("analyze", END)
_compiled = _graph.compile()


async def run(summary: dict) -> dict:
    result = await _compiled.ainvoke({"summary": summary})
    return result["review"]
