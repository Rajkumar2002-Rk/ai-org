from typing import Any

from pydantic import BaseModel


class StartResponse(BaseModel):
    project_id: int
    reply: str
    ui: dict[str, Any]
    stage: str


class MessageRequest(BaseModel):
    project_id: int
    message: str


class MessageResponse(BaseModel):
    reply: str
    ui: dict[str, Any]
    stage: str
    researching: bool = False


class ResearchStatusResponse(BaseModel):
    ready: bool


class PipelineStartRequest(BaseModel):
    project_id: int
    # Optional: switch to the recommended cheaper plan before building.
    plan_override: str | None = None


class PipelineStatusResponse(BaseModel):
    # not_started | running | done | error
    status: str


class ReviewResponse(BaseModel):
    review: dict[str, Any]


class DesignExplanationResponse(BaseModel):
    headline: str
    explanation: str


class BuildStatusResponse(BaseModel):
    status: str  # not_started | running | done | error
    total: int
    complete: int
    files: list[dict[str, Any]]
