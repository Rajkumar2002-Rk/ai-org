"""week 7 devops: secrets (encrypted per-project API keys for injection)

DevOps injects a generated app's API keys as container environment variables.
The values are stored encrypted (Fernet) and are never returned by any API or
written to any log — see app/devops/secrets_store.py.

KNOWN GAP (logged, not a blocker): no onboarding stage populates this table with
real user secrets yet; a proper "connect your API keys" UI is scoped future
work. The table is real and read by DevOps today; it is seeded directly until
that UI exists. Same shape as the requirements.txt gap flagged for Week 7.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "secrets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("key_name", sa.String(length=200), nullable=False),
        sa.Column("value_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "key_name", name="uq_secrets_project_key"),
    )
    op.create_index("ix_secrets_project_id", "secrets", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_secrets_project_id", table_name="secrets")
    op.drop_table("secrets")
