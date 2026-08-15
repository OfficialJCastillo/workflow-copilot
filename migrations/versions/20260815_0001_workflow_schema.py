"""Create the workflow plan and audit schema.

Revision ID: 20260815_0001
Revises:
Create Date: 2026-08-15
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260815_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    table_names = set(inspector.get_table_names())

    if "workflow_plans" not in table_names:
        op.create_table(
            "workflow_plans",
            sa.Column("workflow_id", sa.String(length=32), primary_key=True),
            sa.Column("request_text", sa.Text(), nullable=False),
            sa.Column("requester_role", sa.String(length=120), nullable=False),
            sa.Column("team_name", sa.String(length=160)),
            sa.Column("workflow_type", sa.String(length=80), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("urgency", sa.String(length=32), nullable=False),
            sa.Column("steps_json", sa.JSON(), nullable=False),
            sa.Column("risks_json", sa.JSON(), nullable=False),
            sa.Column("missing_inputs_json", sa.JSON(), nullable=False),
            sa.Column("follow_up_questions_json", sa.JSON(), nullable=False),
            sa.Column("success_checks_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.String(length=40), nullable=False),
            sa.Column("updated_at", sa.String(length=40), nullable=False),
            sa.Column(
                "approval_status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'draft'"),
            ),
            sa.Column("decision_by", sa.String(length=120)),
            sa.Column("decision_note", sa.Text()),
            sa.Column("decided_at", sa.String(length=40)),
        )
    else:
        plan_columns = {column["name"] for column in inspector.get_columns("workflow_plans")}
        legacy_columns = {
            "approval_status": sa.Column(
                "approval_status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'draft'"),
            ),
            "decision_by": sa.Column("decision_by", sa.String(length=120)),
            "decision_note": sa.Column("decision_note", sa.Text()),
            "decided_at": sa.Column("decided_at", sa.String(length=40)),
        }
        for column_name, column in legacy_columns.items():
            if column_name not in plan_columns:
                op.add_column("workflow_plans", column)

    inspector = sa.inspect(connection)
    if "workflow_audit_events" not in set(inspector.get_table_names()):
        op.create_table(
            "workflow_audit_events",
            sa.Column("event_id", sa.String(length=32), primary_key=True),
            sa.Column(
                "workflow_id",
                sa.String(length=32),
                sa.ForeignKey("workflow_plans.workflow_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("event_type", sa.String(length=80), nullable=False),
            sa.Column("actor", sa.String(length=120), nullable=False),
            sa.Column("details_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.String(length=40), nullable=False),
        )

    inspector = sa.inspect(connection)
    audit_indexes = {
        index["name"] for index in inspector.get_indexes("workflow_audit_events")
    }
    if "idx_workflow_audit_events_workflow_created" not in audit_indexes:
        op.create_index(
            "idx_workflow_audit_events_workflow_created",
            "workflow_audit_events",
            ["workflow_id", "created_at"],
        )


def downgrade() -> None:
    op.drop_index(
        "idx_workflow_audit_events_workflow_created",
        table_name="workflow_audit_events",
    )
    op.drop_table("workflow_audit_events")
    op.drop_table("workflow_plans")
