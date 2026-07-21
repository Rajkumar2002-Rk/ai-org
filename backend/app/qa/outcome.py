"""Shared result shape for every QA test (all levels)."""
from dataclasses import dataclass


@dataclass
class TestOutcome:
    """One executed test. `target` is the endpoint/file it exercised, used by
    Level 3 to trace the failure back to the ticket that produced it."""

    name: str
    level: int          # 1 = user interaction, 2 = security attack
    passed: bool
    reason: str = ""
    target: str = ""    # e.g. "POST /orders" or "frontend/app/page.tsx"
    retry_count: int = 0
    root_cause_agent: str | None = None


def failure_is_server_error(status: int) -> bool:
    """A 5xx means the app broke. A 4xx means it correctly REJECTED bad input —
    that is the app working, not a bug."""
    return status >= 500
