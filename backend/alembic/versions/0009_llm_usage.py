"""week 6 verification step 6: llm_usage (measured tokens + cost per call)

codegen.generate() captured no usage anywhere, so every cost figure for this
project was an estimate. This table is the measured basis for a real one.

No backfill is possible and none is attempted: the token counts for past runs
were never captured and are gone. Historical spend stays an estimate; only calls
made from this migration forward are measured.

capture_ok exists so a provider response with no usable usage block is recorded
as UNKNOWN rather than as zero — a silent 0 would understate spend and look like
good news.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("stage", sa.String(length=50), nullable=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model_requested", sa.String(length=100), nullable=False),
        sa.Column("model_used", sa.String(length=100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=8), nullable=True),
        sa.Column("capture_ok", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("fell_back", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # run_id joins these rows to the qa_results rows written by the same pass.
    op.create_index("ix_llm_usage_run_id", "llm_usage", ["run_id"])
    op.create_index("ix_llm_usage_project_id", "llm_usage", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_usage_project_id", table_name="llm_usage")
    op.drop_index("ix_llm_usage_run_id", table_name="llm_usage")
    op.drop_table("llm_usage")
