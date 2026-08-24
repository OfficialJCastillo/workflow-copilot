from pathlib import Path

from fastapi.testclient import TestClient

from app.api import routes
from app.services.copilot import WorkflowCopilot
from app.services.store import WorkflowStore
from main import app


def test_approval_endpoints_expose_state_and_audit_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "copilot",
        WorkflowCopilot(store=WorkflowStore(database_path=str(tmp_path / "workflow.db"))),
    )
    client = TestClient(app)

    created_response = client.post(
        "/workflow/plans",
        json={
            "request_text": "Prepare a customer-facing API release next Thursday with an approval checkpoint.",
            "requester_role": "engineering_manager",
            "team_name": "Platform",
        },
    )
    assert created_response.status_code == 200
    workflow_id = created_response.json()["workflow_id"]

    submitted_response = client.post(
        f"/workflow/plans/{workflow_id}/approval-requests",
        json={"actor": "Jorge Castillo"},
    )
    assert submitted_response.status_code == 200
    assert submitted_response.json()["approval_status"] == "pending_approval"

    decision_response = client.post(
        f"/workflow/plans/{workflow_id}/approval-decisions",
        json={
            "actor": "Release Director",
            "decision": "approved",
            "note": "Release controls are complete.",
        },
    )
    assert decision_response.status_code == 200
    assert decision_response.json()["approval_status"] == "approved"

    audit_response = client.get(f"/workflow/plans/{workflow_id}/audit-events")
    assert audit_response.status_code == 200
    assert [event["event_type"] for event in audit_response.json()] == [
        "plan_created",
        "approval_requested",
        "plan_approved",
    ]


def test_approval_endpoint_rejects_invalid_transition(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "copilot",
        WorkflowCopilot(store=WorkflowStore(database_path=str(tmp_path / "workflow.db"))),
    )
    client = TestClient(app)
    created_response = client.post(
        "/workflow/plans",
        json={
            "request_text": "Prepare a vendor review for the analytics platform contract.",
            "requester_role": "operations_manager",
        },
    )
    workflow_id = created_response.json()["workflow_id"]

    response = client.post(
        f"/workflow/plans/{workflow_id}/approval-decisions",
        json={
            "actor": "Security Reviewer",
            "decision": "rejected",
            "note": "Security questionnaire is incomplete.",
        },
    )

    assert response.status_code == 409
    assert "approval status 'draft'" in response.json()["detail"]


def test_rejection_requires_a_decision_note(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "copilot",
        WorkflowCopilot(store=WorkflowStore(database_path=str(tmp_path / "workflow.db"))),
    )
    client = TestClient(app)
    created_response = client.post(
        "/workflow/plans",
        json={
            "request_text": "Prepare a customer-facing release and identify the final approver.",
            "requester_role": "engineering_manager",
        },
    )
    workflow_id = created_response.json()["workflow_id"]
    client.post(
        f"/workflow/plans/{workflow_id}/approval-requests",
        json={"actor": "Jorge Castillo"},
    )

    response = client.post(
        f"/workflow/plans/{workflow_id}/approval-decisions",
        json={"actor": "Release Director", "decision": "rejected"},
    )

    assert response.status_code == 422
    assert "A rejection note is required." in str(response.json())


def test_readiness_reports_the_database_backend(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "copilot",
        WorkflowCopilot(store=WorkflowStore(database_path=str(tmp_path / "workflow.db"))),
    )
    client = TestClient(app)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "sqlite"}


def test_workflow_input_limits_match_persistence_constraints(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "copilot",
        WorkflowCopilot(store=WorkflowStore(database_path=str(tmp_path / "workflow.db"))),
    )
    client = TestClient(app)

    whitespace_request = client.post(
        "/workflow/plans",
        json={"request_text": "        ", "requester_role": "operator"},
    )
    oversized_role = client.post(
        "/workflow/plans",
        json={
            "request_text": "Prepare a controlled customer release.",
            "requester_role": "r" * 121,
        },
    )
    oversized_team = client.post(
        "/workflow/plans",
        json={
            "request_text": "Prepare a controlled customer release.",
            "requester_role": "operator",
            "team_name": "t" * 161,
        },
    )

    assert whitespace_request.status_code == 422
    assert oversized_role.status_code == 422
    assert oversized_team.status_code == 422


def test_approval_actor_rejects_whitespace_only_values(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "copilot",
        WorkflowCopilot(store=WorkflowStore(database_path=str(tmp_path / "workflow.db"))),
    )
    client = TestClient(app)
    created_response = client.post(
        "/workflow/plans",
        json={
            "request_text": "Prepare a controlled customer release.",
            "requester_role": "operator",
        },
    )
    workflow_id = created_response.json()["workflow_id"]

    response = client.post(
        f"/workflow/plans/{workflow_id}/approval-requests",
        json={"actor": "   "},
    )

    assert response.status_code == 422
