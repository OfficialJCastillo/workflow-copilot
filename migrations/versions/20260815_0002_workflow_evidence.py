"""Add persisted workflow evidence.

Revision ID: 20260815_0002
Revises: 20260815_0001
Create Date: 2026-08-15
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260815_0002"
down_revision: str | None = "20260815_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if "workflow_evidence" not in set(inspector.get_table_names()):
        op.create_table(
            "workflow_evidence",
            sa.Column("evidence_id", sa.String(length=32), primary_key=True),
            sa.Column(
                "workflow_id",
                sa.String(length=32),
                sa.ForeignKey("workflow_plans.workflow_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("media_type", sa.String(length=120), nullable=False),
            sa.Column("content_text", sa.Text(), nullable=False),
            sa.Column("excerpt", sa.Text(), nullable=False),
            sa.Column("source_sha256", sa.String(length=64), nullable=False),
            sa.Column("page_count", sa.Integer()),
            sa.Column("character_count", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.String(length=40), nullable=False),
            sa.UniqueConstraint(
                "workflow_id",
                "source_sha256",
                name="uq_workflow_evidence_workflow_source",
            ),
        )

    inspector = sa.inspect(connection)
    evidence_indexes = {
        index["name"] for index in inspector.get_indexes("workflow_evidence")
    }
    if "idx_workflow_evidence_workflow_created" not in evidence_indexes:
        op.create_index(
            "idx_workflow_evidence_workflow_created",
            "workflow_evidence",
            ["workflow_id", "created_at"],
        )


def downgrade() -> None:
    op.drop_index(
        "idx_workflow_evidence_workflow_created",
        table_name="workflow_evidence",
    )
    op.drop_table("workflow_evidence")
