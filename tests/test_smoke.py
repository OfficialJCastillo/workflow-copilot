from app.schemas.models import WorkflowPlanRequest
from app.services.copilot import WorkflowCopilot


def test_release_plan_smoke() -> None:
    response = WorkflowCopilot().build_plan(
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
    response = WorkflowCopilot().build_plan(
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
