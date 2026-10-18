"""Add retained sector analysis panels without modifying earlier reports.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sector_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("benchmark", sa.String(15), sa.ForeignKey("instruments.symbol"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("request_config", sa.JSON(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
    )
    op.create_index("ix_sector_provider_created", "sector_runs", ["provider", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_sector_provider_created", table_name="sector_runs")
    op.drop_table("sector_runs")
