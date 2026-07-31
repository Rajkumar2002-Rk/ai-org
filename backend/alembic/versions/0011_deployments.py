"""week 7 devops: deployments (one row per deploy attempt)

The spec asked for: id, project_id, live_url, server_type, status, ssl_enabled,
deployed_at, monthly_cost_estimate. The extra columns keep the record HONEST
rather than reassuring (the standing principle of this project):

- auto_fixed / fix_description: a deployment that only came up after an infra
  auto-fix is a DIFFERENT state from a clean success and is shown as such.
- ssl_type: the cert ISSUER, so 'lets_encrypt' (real, AWS) is never confused with
  'self_signed_local' (the local proof). ssl_enabled is never True for a cert we
  did not actually stand up.
- cost_basis: whether monthly_cost_estimate is a projection, an actually-billed
  AWS run, or local $0. A number without its basis is not a measurement.
- security_certified: whether an Opus certificate covered EXACTLY the deployed
  files (drift re-checked at deploy time). Fails closed.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deployments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("blueprint_id", sa.Integer(), nullable=True),
        sa.Column("target", sa.String(length=20), nullable=False,
                  server_default=sa.text("'local'")),
        sa.Column("live_url", sa.String(length=500), nullable=True),
        sa.Column("subdomain", sa.String(length=255), nullable=True),
        sa.Column("region", sa.String(length=50), nullable=True),
        sa.Column("server_type", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False,
                  server_default=sa.text("'deploying'")),
        sa.Column("ssl_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("ssl_type", sa.String(length=30), nullable=True),
        sa.Column("monthly_cost_estimate", sa.Numeric(precision=10, scale=2),
                  nullable=True),
        sa.Column("cost_basis", sa.String(length=50), nullable=True),
        sa.Column("auto_fixed", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("fix_description", sa.Text(), nullable=True),
        sa.Column("security_certified", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("tests_passed", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("health_attempts", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("image_backend_ref", sa.String(length=500), nullable=True),
        sa.Column("image_frontend_ref", sa.String(length=500), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blueprint_id"], ["blueprints.id"],
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deployments_project_id", "deployments", ["project_id"])
    op.create_index("ix_deployments_run_id", "deployments", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_deployments_run_id", table_name="deployments")
    op.drop_index("ix_deployments_project_id", table_name="deployments")
    op.drop_table("deployments")
