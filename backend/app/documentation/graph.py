"""LangGraph wiring for the Documentation agent (one node; the orchestrator owns
the work, matching the QA/DevOps pattern)."""
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.documentation import orchestrator


class DocState(TypedDict, total=False):
    project_id: int
    report: dict[str, Any]


async def _document(state: DocState) -> DocState:
    state["report"] = await orchestrator.run(state["project_id"])
    return state


_graph = StateGraph(DocState)
_graph.add_node("document", _document)
_graph.add_edge(START, "document")
_graph.add_edge("document", END)
_compiled = _graph.compile()


async def run(project_id: int) -> dict:
    result = await _compiled.ainvoke({"project_id": project_id})
    return result["report"]
