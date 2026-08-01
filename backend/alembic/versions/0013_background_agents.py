"""week 9 background agents: monitoring_logs, deployment_snapshots, fix_logs,
user_issues, cost_logs

Monitoring (#13), Auto-fix (#14, Safe Mode snapshots + rollback), Cost Tracker
(#15). All post-launch, background; the user sees them only via the dashboard.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "monitoring_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("is_healthy", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_monitoring_logs_project_id", "monitoring_logs", ["project_id"])
    op.create_index("ix_monitoring_logs_checked_at", "monitoring_logs", ["checked_at"])

    op.create_table(
        "deployment_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("deployment_id", sa.Integer(), nullable=True),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deployment_snapshots_project_id", "deployment_snapshots",
                    ["project_id"])

    op.create_table(
        "fix_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("problem", sa.Text(), nullable=True),
        sa.Column("action", sa.String(length=255), nullable=True),
        sa.Column("snapshot_id", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=50), nullable=False),
        sa.Column("downtime_seconds", sa.Integer(), nullable=True),
        sa.Column("notified", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("notification", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["deployment_snapshots.id"],
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fix_logs_project_id", "fix_logs", ["project_id"])

    op.create_table(
        "user_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default=sa.text("'open'")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_issues_project_id", "user_issues", ["project_id"])

    op.create_table(
        "cost_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.String(length=10), nullable=False),
        sa.Column("actual_cost_usd", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("projected_monthly_usd", sa.Numeric(precision=10, scale=2),
                  nullable=True),
        sa.Column("budget_usd", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("over_budget", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cost_logs_project_id", "cost_logs", ["project_id"])


def downgrade() -> None:
    for t in ("cost_logs", "user_issues", "fix_logs", "deployment_snapshots",
              "monitoring_logs"):
        op.drop_table(t)
