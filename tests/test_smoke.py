from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import inspect

from app.schemas.models import WorkflowPlanRequest
from app.services.copilot import WorkflowCopilot
from app.services.store import WorkflowStore
from app.services.store import InvalidApprovalTransition


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_release_plan_smoke() -> None:
    response = WorkflowCopilot(store=WorkflowStore(database_path=":memory:")).build_plan(
        WorkflowPlanRequest(
            request_text="Prepare a minor release for a customer-facing API next Thursday.",
            requester_role="engineering_manager",
            team_name="Platform",
        )
    )
    assert response.workflow_type == "release_preparation"
    assert response.urgency == "high"
    assert "customer-facing release" in response.summary.lower()
    assert response.steps
    assert any(step.owner == "release manager" for step in response.steps)
    assert any("rollback" in check.lower() for check in response.success_checks)


def test_release_with_rollback_language_is_not_misclassified_as_incident() -> None:
    response = WorkflowCopilot(store=WorkflowStore(database_path=":memory:")).build_plan(
        WorkflowPlanRequest(
            request_text=(
                "Prepare a customer-facing API release next Friday with owner assignments, "
                "rollback criteria, and final approval."
            ),
            requester_role="release_lead",
            team_name="Platform",
        )
    )

    assert response.workflow_type == "release_preparation"


def test_incident_plan_smoke() -> None:
    response = WorkflowCopilot(store=WorkflowStore(database_path=":memory:")).build_plan(
        WorkflowPlanRequest(
            request_text="We have an outage today and need a rollback plan immediately.",
            requester_role="sre_manager",
            team_name="Reliability",
        )
    )
    assert response.workflow_type == "incident_response"
    assert response.urgency == "high"
    assert response.risks
    assert any("service" in question.lower() or "affected" in question.lower() for question in response.follow_up_questions)


def test_vendor_plan_flags_conflicting_timeline_and_budget_gap() -> None:
    response = WorkflowCopilot(store=WorkflowStore(database_path=":memory:")).build_plan(
        WorkflowPlanRequest(
            request_text="Urgent vendor security review needed ASAP for next quarter analytics contract.",
            requester_role="operations_manager",
            team_name="Operations",
        )
    )

    assert response.workflow_type == "vendor_approval"
    assert response.urgency == "high"
    assert any("optimize for the wrong date" in risk.lower() for risk in response.risks)
    assert any("budget owner or expected spend range" in item.lower() for item in response.missing_inputs)
    assert any("which date should the team optimize for" in question.lower() for question in response.follow_up_questions)
    assert any("budget owner or spend range" in question.lower() for question in response.follow_up_questions)


def test_remote_onboarding_adds_location_and_setup_questions() -> None:
    response = WorkflowCopilot(store=WorkflowStore(database_path=":memory:")).build_plan(
        WorkflowPlanRequest(
            request_text="Prepare remote onboarding for a new hire joining next Monday.",
            requester_role="people_ops_manager",
            team_name="People Operations",
        )
    )

    assert response.workflow_type == "onboarding"
    assert "remote setup" in response.summary.lower()
    assert any("work location or time zone" in item.lower() for item in response.missing_inputs)
    assert any("distributed onboarding" in risk.lower() for risk in response.risks)
    assert any("week one" in question.lower() for question in response.follow_up_questions)
    assert any("remote setup tasks" in question.lower() for question in response.follow_up_questions)


def test_persisted_plan_can_be_retrieved_and_updated(tmp_path: Path) -> None:
    store = WorkflowStore(database_path=str(tmp_path / "workflow.db"))
    copilot = WorkflowCopilot(store=store)
    created = copilot.create_plan(
        WorkflowPlanRequest(
            request_text="Prepare a minor release for a customer-facing API next Thursday.",
            requester_role="engineering_manager",
            team_name="Platform",
        )
    )

    listed = copilot.list_plans()
    assert len(listed) == 1
    assert listed[0].workflow_id == created.workflow_id
    assert listed[0].total_step_count == len(created.steps)
    assert listed[0].completed_step_count == 0
    assert listed[0].step_status_counts["pending"] == len(created.steps)

    fetched = copilot.get_plan(created.workflow_id)
    assert fetched is not None
    assert fetched.request_text == created.request_text

    updated = copilot.update_step_status(created.workflow_id, created.steps[0].step_id, "completed")
    assert updated is not None
    assert updated.steps[0].status == "completed"

    refetched = copilot.get_plan(created.workflow_id)
    assert refetched is not None
    assert refetched.steps[0].status == "completed"

    relisted = copilot.list_plans()
    assert relisted[0].workflow_id == created.workflow_id
    assert relisted[0].completed_step_count == 1
    assert relisted[0].total_step_count == len(created.steps)
    assert relisted[0].step_status_counts["completed"] == 1


def test_plan_approval_lifecycle_is_auditable(tmp_path: Path) -> None:
    copilot = WorkflowCopilot(store=WorkflowStore(database_path=str(tmp_path / "workflow.db")))
    created = copilot.create_plan(
        WorkflowPlanRequest(
            request_text="Prepare a customer-facing API release next Thursday with an approval checkpoint.",
            requester_role="engineering_manager",
            team_name="Platform",
        )
    )

    assert created.approval_status == "draft"
    submitted = copilot.submit_for_approval(created.workflow_id, actor="Jorge Castillo")
    assert submitted is not None
    assert submitted.approval_status == "pending_approval"

    approved = copilot.decide_plan(
        created.workflow_id,
        decision="approved",
        actor="Release Director",
        note="Rollback owner and verification window are confirmed.",
    )
    assert approved is not None
    assert approved.approval_status == "approved"
    assert approved.decision_by == "Release Director"
    assert approved.decision_note == "Rollback owner and verification window are confirmed."
    assert approved.decided_at is not None

    events = copilot.list_audit_events(created.workflow_id)
    assert events is not None
    assert [event.event_type for event in events] == [
        "plan_created",
        "approval_requested",
        "plan_approved",
    ]
    assert events[-1].actor == "Release Director"
    assert events[-1].details["approval_status"] == "approved"


def test_plan_cannot_be_decided_before_submission(tmp_path: Path) -> None:
    copilot = WorkflowCopilot(store=WorkflowStore(database_path=str(tmp_path / "workflow.db")))
    created = copilot.create_plan(
        WorkflowPlanRequest(
            request_text="Prepare a vendor review for the analytics platform contract.",
            requester_role="operations_manager",
        )
    )

    with pytest.raises(InvalidApprovalTransition, match="approval status 'draft'"):
        copilot.decide_plan(
            created.workflow_id,
            decision="rejected",
            actor="Security Reviewer",
            note="Security questionnaire is incomplete.",
        )


def test_alembic_migrates_existing_plan_database(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "legacy-workflow.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE workflow_plans (
                workflow_id TEXT PRIMARY KEY,
                request_text TEXT NOT NULL,
                requester_role TEXT NOT NULL,
                team_name TEXT,
                workflow_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                urgency TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                risks_json TEXT NOT NULL,
                missing_inputs_json TEXT NOT NULL,
                follow_up_questions_json TEXT NOT NULL,
                success_checks_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    monkeypatch.setenv(
        "WORKFLOW_DATABASE_URL",
        f"sqlite+pysqlite:///{database_path}",
    )
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(config, "head")

    with sqlite3.connect(database_path) as connection:
        plan_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(workflow_plans)").fetchall()
        }
        audit_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'workflow_audit_events'"
        ).fetchone()
        migration_version = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()

    assert {"approval_status", "decision_by", "decision_note", "decided_at"} <= plan_columns
    assert audit_table is not None
    assert migration_version == ("20260815_0002",)


def test_alembic_creates_the_current_schema(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "fresh-workflow.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    monkeypatch.setenv("WORKFLOW_DATABASE_URL", database_url)

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    command.check(config)
    store = WorkflowStore(database_url=database_url, initialize_schema=False)
    table_names = set(inspect(store.engine).get_table_names())

    assert {
        "alembic_version",
        "workflow_plans",
        "workflow_audit_events",
        "workflow_evidence",
    } <= table_names
    store.check_connection()
