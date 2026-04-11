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
    assert response.urgency == "medium"
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

    fetched = copilot.get_plan(created.workflow_id)
    assert fetched is not None
    assert fetched.request_text == created.request_text

    updated = copilot.update_step_status(created.workflow_id, created.steps[0].step_id, "completed")
    assert updated is not None
    assert updated.steps[0].status == "completed"

    refetched = copilot.get_plan(created.workflow_id)
    assert refetched is not None
    assert refetched.steps[0].status == "completed"
