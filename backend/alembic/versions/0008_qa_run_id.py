"""week 6 verification: qa_results.run_id (group rows by QA pass)

A project is re-tested repeatedly and blueprint_id does NOT disambiguate those
re-runs, so separating one pass from another meant matching created_at by hand.
Existing rows are backfilled: every distinct (project_id, created_at) pair was
one pass, so that pair deterministically seeds its run_id.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("qa_results", sa.Column("run_id", sa.String(length=36), nullable=True))

    # Backfill historical rows so past verification data is groupable too.
    op.execute(
        """
        UPDATE qa_results q
           SET run_id = g.rid
        FROM (
            SELECT DISTINCT project_id, created_at,
                   md5(project_id::text || '|' || created_at::text) AS rid
            FROM qa_results
        ) g
        WHERE q.project_id = g.project_id AND q.created_at = g.created_at
        """
    )
    op.create_index("ix_qa_results_run_id", "qa_results", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_qa_results_run_id", table_name="qa_results")
    op.drop_column("qa_results", "run_id")
