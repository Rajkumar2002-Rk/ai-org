"""week 5: code_reviews table (Code Reviewer agent)

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "code_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("issues_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("issues_fixed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("security_passed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reviewed_by_model", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["generated_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_reviews_project_id", "code_reviews", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_code_reviews_project_id", table_name="code_reviews")
    op.drop_table("code_reviews")
