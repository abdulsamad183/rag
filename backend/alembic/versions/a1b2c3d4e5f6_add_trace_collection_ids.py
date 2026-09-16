"""Add collection_ids to retrieval_traces for cost/latency dashboards.

Revision ID: a1b2c3d4e5f6
Revises: eb4cea17258e
Create Date: 2026-09-16 20:30:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = "eb4cea17258e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "retrieval_traces",
        sa.Column(
            "collection_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("retrieval_traces", "collection_ids", server_default=None)


def downgrade() -> None:
    op.drop_column("retrieval_traces", "collection_ids")
