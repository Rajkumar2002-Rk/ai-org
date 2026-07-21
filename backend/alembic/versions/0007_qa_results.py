"""week 6: qa_results table (QA agent)

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qa_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        # Pins each result to the blueprint version that was tested, so a later
        # re-test can be compared against the same blueprint.
        sa.Column("blueprint_id", sa.Integer(), nullable=True),
        sa.Column("test_name", sa.String(length=255), nullable=False),
        sa.Column("test_level", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("root_cause_agent", sa.String(length=50), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blueprint_id"], ["blueprints.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_qa_results_project_id", "qa_results", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_qa_results_project_id", table_name="qa_results")
    op.drop_table("qa_results")
