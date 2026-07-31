"""Where the deployment's monthly cost estimate comes from.

NOT parroted from the blueprint's `estimated_monthly_cost_usd` (that is the
Architect's rough per-tier guess). The number on a `deployments` row is computed
from the CONCRETE resources DevOps chose — the specific EC2 instance type (or
Fargate task size), the public IPv4 charge, EBS, the hosted zone — so it is
reproducible from `server_type` and recomputable if a rate changes.

Two honesty rules, both from this project's standing principle:

* **A number without its basis is not a measurement.** Every estimate carries a
  `cost_basis`: `projected_aws_<tier>` for a local run (we show the honest
  projected hosting cost, never local-$0 dressed up as the price), or
  `billed_aws_<server>` for a real AWS deployment.
* **A rate that silently goes stale is a check that cannot fail.** AWS prices
  drift; `_RATE_ASOF` is an active tripwire the test suite asserts on, so the
  suite starts failing once the rates are too old to trust and names the fix —
  exactly like `usage._RATE_EXPIRY`.

Rates are us-east-2 on-demand, confirmed 2026-07-30.
"""
from dataclasses import dataclass
from datetime import date

# ---------------------------------------------------------------- rate table
_RATE_ASOF = "2026-07-30"
# Beyond this age the rates are no longer trustworthy without re-confirmation.
_RATE_MAX_AGE_DAYS = 180

_HOURS_PER_MONTH = 730

# EC2 on-demand $/hour, us-east-2.
_EC2_HOURLY = {
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
}
# Public IPv4 address — charged $0.005/hr since 2024 even while attached. This is
# the fixed cost people forget; it is called out on its own line for that reason.
_PUBLIC_IPV4_HOURLY = 0.005
# EBS gp3 root volume.
_EBS_GP3_PER_GB = 0.08
_DEFAULT_ROOT_GB = 8
# Route53 public hosted zone (shared across all apps; per-app marginal, included
# small so the estimate never understates).
_ROUTE53_ZONE = 0.50
# Fargate (us-east-2).
_FARGATE_VCPU_HOUR = 0.04048
_FARGATE_GB_HOUR = 0.004445
# Application Load Balancer base (LCUs negligible at demo scale).
_ALB_HOURLY = 0.0225
# A managed database for the "large" tier (db.t3.small, single-AZ).
_RDS_MONTHLY = 24.00


@dataclass
class CostEstimate:
    monthly_usd: float
    basis: str
    breakdown: dict[str, float]


def rates_stale(today: str | None = None) -> bool:
    """True once the rate table is older than `_RATE_MAX_AGE_DAYS`. Asserted by
    the test suite so stale AWS prices surface loudly instead of quietly."""
    today = today or date.today().isoformat()
    d0 = date.fromisoformat(_RATE_ASOF)
    d1 = date.fromisoformat(today)
    return (d1 - d0).days > _RATE_MAX_AGE_DAYS


def _round(x: float) -> float:
    return round(x, 2)


def _ec2_single_breakdown(instance_type: str) -> dict[str, float]:
    hourly = _EC2_HOURLY.get(instance_type)
    if hourly is None:
        # No confirmed rate -> do not invent one; the caller reports it.
        return {}
    return {
        f"ec2 {instance_type}": _round(hourly * _HOURS_PER_MONTH),
        "public ipv4": _round(_PUBLIC_IPV4_HOURLY * _HOURS_PER_MONTH),
        "ebs gp3 root": _round(_EBS_GP3_PER_GB * _DEFAULT_ROOT_GB),
        "route53 zone": _ROUTE53_ZONE,
    }


def _ecs_breakdown(vcpu: float, gb: float) -> dict[str, float]:
    return {
        "fargate vcpu": _round(_FARGATE_VCPU_HOUR * vcpu * _HOURS_PER_MONTH),
        "fargate memory": _round(_FARGATE_GB_HOUR * gb * _HOURS_PER_MONTH),
        "load balancer": _round(_ALB_HOURLY * _HOURS_PER_MONTH),
        "rds database": _RDS_MONTHLY,
        "public ipv4": _round(_PUBLIC_IPV4_HOURLY * _HOURS_PER_MONTH),
        "route53 zone": _ROUTE53_ZONE,
    }


def estimate(sizing, target: str) -> CostEstimate:
    """Compute the monthly estimate for a `sizing.Sizing` and a deploy target.

    `target='local'` returns the PROJECTED cost of the equivalent AWS tier (basis
    projected_aws_<tier>) — the honest hosting cost, clearly not an actual bill.
    `target='aws'` returns the same computation with basis billed_aws_<server>.
    """
    if sizing.strategy == "ecs":
        # Parse the blueprint's "4 vCPU, 8 GB RAM + load balancer" descriptor,
        # defaulting to the large tier's 4 vCPU / 8 GB.
        breakdown = _ecs_breakdown(4.0, 8.0)
        server_key = "ecs_fargate_4vcpu_8gb"
    else:
        breakdown = _ec2_single_breakdown(sizing.instance_type or "")
        server_key = (sizing.instance_type or "unknown").replace(".", "_")

    monthly = _round(sum(breakdown.values())) if breakdown else 0.0
    basis = (f"projected_aws_{sizing.tier}" if target == "local"
             else f"billed_aws_{server_key}")
    return CostEstimate(monthly_usd=monthly, basis=basis, breakdown=breakdown)
