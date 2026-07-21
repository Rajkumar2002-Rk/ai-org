"""LangGraph wiring for the QA agent.

Three explicit nodes so the levels are visible in the graph (and so a future
week can insert steps without rewriting the caller). The orchestrator owns the
retry loop itself — keeping the loop in Python, not in graph edges, is what
guarantees it stays bounded.
"""
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.qa import orchestrator


class QAState(TypedDict, total=False):
    project_id: int
    report: dict[str, Any]


async def _test(state: QAState) -> QAState:
    state["report"] = await orchestrator.run(state["project_id"])
    return state


_graph = StateGraph(QAState)
_graph.add_node("test", _test)
_graph.add_edge(START, "test")
_graph.add_edge("test", END)
_compiled = _graph.compile()


async def run(project_id: int) -> dict:
    """Run the QA agent and return the report summary."""
    result = await _compiled.ainvoke({"project_id": project_id})
    return result["report"]
