from pathlib import Path

from fastapi.testclient import TestClient

from app.api import routes
from app.services.copilot import WorkflowCopilot
from app.services.retrieval import EvidenceRetriever
from app.services.retrieval import SearchDocument
from app.services.store import WorkflowStore
from main import app
from scripts.evaluate_retrieval import evaluate_records
from scripts.validate_evaluation_dataset import DEFAULT_DATASET
from scripts.validate_evaluation_dataset import load_and_validate_dataset


def test_retriever_ranks_grounded_rollback_source_first() -> None:
    documents = [
        SearchDocument(
            source_id="release-brief",
            citation_id="SRC-RELEASE",
            filename="release-brief.txt",
            content="Rollback owner is Platform SRE. Trigger rollback above two percent errors.",
        ),
        SearchDocument(
            source_id="support-plan",
            citation_id="SRC-SUPPORT",
            filename="support-plan.txt",
            content="Customer Support coverage begins at 20:30 UTC.",
        ),
    ]

    result = EvidenceRetriever().search(
        query="Who owns rollback and what is the error threshold?",
        documents=documents,
        top_k=2,
    )

    assert result.total_chunks == 2
    assert result.results[0].source_id == "release-brief"
    assert {"rollback", "owner"} <= set(result.results[0].matched_terms)
    assert result.results[0].rerank_score >= result.results[0].retrieval_score


def test_retriever_abstains_without_lexical_support() -> None:
    result = EvidenceRetriever().search(
        query="Who authorized emergency rollback?",
        documents=[
            SearchDocument(
                source_id="directory",
                citation_id="SRC-DIR",
                filename="directory.txt",
                content="Regional office telephone numbers and meeting room locations.",
            )
        ],
    )

    assert result.total_chunks == 1
    assert result.results == ()


def test_search_endpoint_returns_ranked_citations(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "copilot",
        WorkflowCopilot(store=WorkflowStore(database_path=str(tmp_path / "workflow.db"))),
    )
    client = TestClient(app)
    created = client.post(
        "/workflow/plans",
        json={
            "request_text": "Prepare a release with rollback controls.",
            "requester_role": "release lead",
        },
    ).json()
    workflow_id = created["workflow_id"]
    uploaded = client.post(
        f"/workflow/plans/{workflow_id}/evidence",
        files={
            "file": (
                "rollback.txt",
                b"Rollback owner is Platform SRE. Error threshold is two percent.",
                "text/plain",
            )
        },
        data={"actor": "Jordan Lee"},
    ).json()

    response = client.post(
        f"/workflow/plans/{workflow_id}/evidence/search",
        json={"query": "rollback owner error threshold", "top_k": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy"] == "lexical"
    assert payload["evidence_found"] is True
    assert payload["source_count"] == 1
    assert payload["total_chunks"] == 1
    assert payload["results"][0]["evidence_id"] == uploaded["evidence_id"]
    assert payload["results"][0]["citation_id"] == uploaded["citation_id"]
    assert payload["results"][0]["matched_terms"] == [
        "rollback",
        "owner",
        "error",
        "threshold",
    ]

    hybrid_response = client.post(
        f"/workflow/plans/{workflow_id}/evidence/search",
        json={
            "query": "Who is accountable for the backout?",
            "strategy": "hybrid",
            "top_k": 3,
        },
    )
    assert hybrid_response.status_code == 200
    assert hybrid_response.json()["strategy"] == "hybrid"
    assert hybrid_response.json()["results"][0]["evidence_id"] == uploaded["evidence_id"]

    abstention_response = client.post(
        f"/workflow/plans/{workflow_id}/evidence/search",
        json={
            "query": "Who authorized the emergency rollback?",
            "strategy": "hybrid",
        },
    )
    assert abstention_response.status_code == 200
    assert abstention_response.json()["evidence_found"] is False
    assert abstention_response.json()["abstention_reason"] == (
        "compound_intent_not_supported"
    )
    assert abstention_response.json()["required_terms"] == ["approval", "rollback"]


def test_synthetic_retrieval_baseline_meets_minimum_quality() -> None:
    results = evaluate_records(
        load_and_validate_dataset(DEFAULT_DATASET),
        top_k=3,
        runs_per_case=2,
    )

    assert results["quality"]["source_recall_at_k"] >= 0.8
    assert results["quality"]["mean_reciprocal_rank"] >= 0.8
    assert results["quality"]["evidence_absence_accuracy"] == 1.0
