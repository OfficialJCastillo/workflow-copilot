import os
from pathlib import Path

from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import JSON
from sqlalchemy import MetaData
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy import Text
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool


DEFAULT_DATABASE_URL = "sqlite+pysqlite:///data/workflow_copilot.db"

metadata = MetaData()

workflow_plans = Table(
    "workflow_plans",
    metadata,
    Column("workflow_id", String(32), primary_key=True),
    Column("request_text", Text, nullable=False),
    Column("requester_role", String(120), nullable=False),
    Column("team_name", String(160)),
    Column("workflow_type", String(80), nullable=False),
    Column("summary", Text, nullable=False),
    Column("urgency", String(32), nullable=False),
    Column("steps_json", JSON, nullable=False),
    Column("risks_json", JSON, nullable=False),
    Column("missing_inputs_json", JSON, nullable=False),
    Column("follow_up_questions_json", JSON, nullable=False),
    Column("success_checks_json", JSON, nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Column("approval_status", String(32), nullable=False, server_default="draft"),
    Column("decision_by", String(120)),
    Column("decision_note", Text),
    Column("decided_at", String(40)),
)

workflow_audit_events = Table(
    "workflow_audit_events",
    metadata,
    Column("event_id", String(32), primary_key=True),
    Column(
        "workflow_id",
        String(32),
        ForeignKey("workflow_plans.workflow_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("event_type", String(80), nullable=False),
    Column("actor", String(120), nullable=False),
    Column("details_json", JSON, nullable=False),
    Column("created_at", String(40), nullable=False),
)

Index(
    "idx_workflow_audit_events_workflow_created",
    workflow_audit_events.c.workflow_id,
    workflow_audit_events.c.created_at,
)


def database_url_from_path(database_path: str) -> str:
    if database_path == ":memory:":
        return "sqlite+pysqlite:///:memory:"
    return f"sqlite+pysqlite:///{Path(database_path)}"


def configured_database_url() -> str:
    return os.getenv("WORKFLOW_DATABASE_URL", DEFAULT_DATABASE_URL)


def create_database_engine(database_url: str | None = None) -> Engine:
    resolved_url = database_url or configured_database_url()
    parsed_url = make_url(resolved_url)
    options: dict[str, object] = {"pool_pre_ping": True}

    if parsed_url.get_backend_name() == "sqlite":
        options["connect_args"] = {"check_same_thread": False}
        if parsed_url.database and parsed_url.database != ":memory:":
            Path(parsed_url.database).parent.mkdir(parents=True, exist_ok=True)
        if parsed_url.database == ":memory:":
            options["poolclass"] = StaticPool

    return create_engine(resolved_url, **options)
