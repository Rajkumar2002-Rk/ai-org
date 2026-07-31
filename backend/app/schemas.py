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


class SecurityStatusResponse(BaseModel):
    status: str  # not_started | running | done | error
    certificate: dict[str, Any] | None = None


class QAStatusResponse(BaseModel):
    """Counts only — no test names, no technical detail reaches the user."""

    status: str  # not_started | running | done | error
    total: int = 0
    passed: int = 0
    failed: int = 0


class DeployStatusResponse(BaseModel):
    """The climax screen's data. No code, agent, or model names — only what a
    non-technical user should see. Secret VALUES are never included (only the
    live URL, badges, and the honest cost)."""

    status: str  # not_started | running | live | failed | blocked | error
    live_url: str | None = None
    ssl_enabled: bool = False
    # lets_encrypt | self_signed_local | none — the ISSUER, recorded honestly.
    ssl_type: str | None = None
    security_certified: bool = False
    tests_passed: int = 0
    monthly_cost_estimate: float | None = None
    # projected_aws_<tier> | billed_aws_<server> | local_zero
    cost_basis: str | None = None
    server_type: str | None = None
    # A deployment that only came up after an automatic fix is shown as such,
    # never laundered into looking like a clean first-pass success.
    auto_fixed: bool = False
    # Present on a blocked/failed deploy so the reason travels with the status.
    reason: str | None = None
