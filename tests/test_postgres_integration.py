import os

import pytest

from app.schemas.models import WorkflowPlanRequest
from app.services.copilot import WorkflowCopilot
from app.services.store import WorkflowStore


POSTGRES_TEST_URL = os.getenv("TEST_POSTGRES_DATABASE_URL")


@pytest.mark.skipif(
    POSTGRES_TEST_URL is None,
    reason="TEST_POSTGRES_DATABASE_URL is not configured.",
)
def test_postgres_persists_the_approval_lifecycle() -> None:
    store = WorkflowStore(
        database_url=POSTGRES_TEST_URL,
        initialize_schema=False,
    )
    copilot = WorkflowCopilot(store=store)

    created = copilot.create_plan(
        WorkflowPlanRequest(
            request_text="Prepare the PostgreSQL-backed customer API release next Thursday.",
            requester_role="integration_test",
            team_name="Platform",
        )
    )
    updated = copilot.update_step_status(
        created.workflow_id,
        created.steps[0].step_id,
        "completed",
        actor="integration_test",
    )
    submitted = copilot.submit_for_approval(created.workflow_id, actor="integration_test")
    approved = copilot.decide_plan(
        created.workflow_id,
        decision="approved",
        actor="integration_reviewer",
        note="PostgreSQL persistence verified.",
    )
    events = copilot.list_audit_events(created.workflow_id)

    assert store.database_backend == "postgresql"
    assert updated is not None and updated.steps[0].status == "completed"
    assert submitted is not None and submitted.approval_status == "pending_approval"
    assert approved is not None and approved.approval_status == "approved"
    assert events is not None
    assert [event.event_type for event in events] == [
        "plan_created",
        "step_status_updated",
        "approval_requested",
        "plan_approved",
    ]
