"""LangGraph wiring for the DevOps agent.

One node for now; the orchestrator owns the ordering and the bounded auto-fix in
Python (keeping the loop out of graph edges is what keeps it bounded — the same
choice QA made). A future week can insert nodes (monitoring hand-off, docs) here
without touching the caller.
"""
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.devops import orchestrator


class DeployState(TypedDict, total=False):
    project_id: int
    report: dict[str, Any]


async def _deploy(state: DeployState) -> DeployState:
    state["report"] = await orchestrator.run(state["project_id"])
    return state


_graph = StateGraph(DeployState)
_graph.add_node("deploy", _deploy)
_graph.add_edge(START, "deploy")
_graph.add_edge("deploy", END)
_compiled = _graph.compile()


async def run(project_id: int) -> dict:
    result = await _compiled.ainvoke({"project_id": project_id})
    return result["report"]
