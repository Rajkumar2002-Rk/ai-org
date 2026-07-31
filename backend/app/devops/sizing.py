"""STEP 1 — read the blueprint's cloud_config and choose a concrete server.

The Architect already sized the app into a tier ("small" / "medium" / "large")
from expected users and budget (architect/builder._decide_tier). DevOps does NOT
re-decide that; it maps the tier to a CONCRETE deployment shape and records the
reasoning so the choice is auditable:

    small  -> single EC2 t3.micro   (per the spec: "small personal apps")
    medium -> single EC2 t3.small
    large  -> ECS Fargate + autoscaling ("larger apps: ECS with a task def")

It also reads expected_users + budget back out (from the summary the tier was
derived from) purely to (a) build a human rationale and (b) flag a mismatch — if
the blueprint says "small" but expected users are enormous, that is surfaced, not
silently deployed onto a t3.micro. Flagging, not overriding: the Architect owns
sizing; DevOps refuses to invent a different answer.
"""
from dataclasses import dataclass, field

from app.config import settings


@dataclass
class Sizing:
    tier: str
    strategy: str            # "ec2_single" | "ecs"
    instance_type: str | None
    autoscaling: bool
    server_type: str         # human descriptor recorded on the deployment row
    server_size: str         # the blueprint's vCPU/RAM string
    expected_users: int | None
    budget_usd: int | None
    rationale: str
    warnings: list[str] = field(default_factory=list)


def _to_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def decide(blueprint: dict, summary: dict | None = None) -> Sizing:
    summary = summary or {}
    cloud = (blueprint or {}).get("cloud_config", {}) or {}
    tier = cloud.get("tier", "medium")
    server_size = cloud.get("server_size", "unknown")
    expected_users = _to_int(summary.get("user_count"))
    budget = _to_int(summary.get("budget"))

    if tier == "large":
        strategy, instance_type, autoscaling = "ecs", None, True
        server_type = "ECS Fargate (autoscaling)"
    elif tier == "medium":
        strategy = "ec2_single"
        instance_type = settings.ec2_instance_medium
        autoscaling = False
        server_type = f"EC2 {instance_type}"
    else:  # small (and any unknown tier -> safest/cheapest)
        strategy = "ec2_single"
        instance_type = settings.ec2_instance_small
        autoscaling = False
        server_type = f"EC2 {instance_type}"

    warnings: list[str] = []
    # A tier/scale mismatch is surfaced, never silently deployed onto a tiny box.
    if tier != "large" and expected_users is not None and expected_users >= 100_000:
        warnings.append(
            f"Blueprint tier is '{tier}' but expected_users is {expected_users:,}; "
            f"the Architect's sizing looks low for that scale."
        )

    rationale = (
        f"Tier '{tier}' ({server_size}) -> {server_type}. "
        f"expected_users={expected_users if expected_users is not None else 'n/a'}, "
        f"budget={('$' + str(budget)) if budget is not None else 'n/a'}."
    )

    return Sizing(
        tier=tier,
        strategy=strategy,
        instance_type=instance_type,
        autoscaling=autoscaling,
        server_type=server_type,
        server_size=server_size,
        expected_users=expected_users,
        budget_usd=budget,
        rationale=rationale,
        warnings=warnings,
    )
