from pathlib import Path

from app.schemas.models import WorkflowPlanRequest
from app.services.copilot import WorkflowCopilot
from app.services.store import WorkflowStore


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
