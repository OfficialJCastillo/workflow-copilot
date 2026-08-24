from pathlib import Path

from fastapi.testclient import TestClient

from app.api import routes
from app.services.copilot import WorkflowCopilot
from app.services.grounding import GroundedAnswerService
from app.services.hybrid_retrieval import HybridEvidenceRetriever
from app.services.retrieval import SearchDocument
from app.services.store import WorkflowStore
from main import app
from scripts.evaluate_grounding import evaluate_grounded_answers
from scripts.validate_evaluation_dataset import DEFAULT_DATASET
from scripts.validate_evaluation_dataset import load_and_validate_dataset


CHALLENGE_DATASET = (
    Path(__file__).resolve().parents[1]
    / "evaluation"
    / "datasets"
    / "workflow_evidence_challenge_v1.jsonl"
)
CONTEXT_POLICY_DATASET = (
    Path(__file__).resolve().parents[1]
    / "evaluation"
    / "datasets"
    / "workflow_evidence_context_policy_v1.jsonl"
)


def test_grounded_answer_only_emits_cited_source_claims() -> None:
    result = GroundedAnswerService().answer(
        query="Who owns rollback and what threshold applies?",
        documents=[
            SearchDocument(
                source_id="release-brief",
                citation_id="SRC-RELEASE",
                filename="release-brief.txt",
                content=(
                    "Rollback owner is Platform SRE. "
                    "Trigger rollback above two percent errors."
                ),
            )
        ],
    )

    assert result.status == "grounded"
    assert [claim.text for claim in result.claims] == [
        "Rollback owner is Platform SRE.",
        "Trigger rollback above two percent errors.",
    ]
    assert all(claim.citation_id == "SRC-RELEASE" for claim in result.claims)
    assert "[SRC-RELEASE]" in result.answer


def test_grounded_answer_adds_support_that_completes_core_query_coverage() -> None:
    result = GroundedAnswerService(HybridEvidenceRetriever()).answer(
        query=(
            "Prepare the customer API release for Thursday and confirm "
            "rollback readiness."
        ),
        documents=[
            SearchDocument(
                source_id="release-brief",
                citation_id="SRC-RELEASE",
                filename="release-brief.txt",
                content=(
                    "Deployment window: Thursday 21:00 UTC. "
                    "Rollback owner: Platform SRE. "
                    "Rollback trigger: error rate above 2% for five minutes."
                ),
            ),
            SearchDocument(
                source_id="support-plan",
                citation_id="SRC-SUPPORT",
                filename="support-plan.txt",
                content=(
                    "Customer Support coverage is confirmed from 20:30 UTC "
                    "through 23:00 UTC."
                ),
            ),
        ],
    )

    assert {claim.source_id for claim in result.claims} == {
        "release-brief",
        "support-plan",
    }
    assert result.context_policy == "strong_plus_supporting"
    assert result.excluded_result_count == 0


def test_grounded_answer_labels_partial_and_insufficient_evidence() -> None:
    service = GroundedAnswerService()
    partial = service.answer(
        query="Approve the production release tomorrow.",
        documents=[
            SearchDocument(
                source_id="scope",
                citation_id="SRC-SCOPE",
                filename="scope.txt",
                content="Release scope includes the billing API.",
            )
        ],
    )
    insufficient = service.answer(
        query="Who approved the emergency rollback threshold?",
        documents=[
            SearchDocument(
                source_id="directory",
                citation_id="SRC-DIR",
                filename="directory.txt",
                content="Office telephone numbers and meeting room locations.",
            )
        ],
    )

    assert partial.status == "partial_evidence"
    assert "Additional evidence is required" in partial.answer
    assert insufficient.status == "insufficient_evidence"
    assert insufficient.claims == ()


def test_grounded_answer_endpoint_returns_structured_claims(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "copilot",
        WorkflowCopilot(store=WorkflowStore(database_path=str(tmp_path / "workflow.db"))),
    )
    client = TestClient(app)
    workflow_id = client.post(
        "/workflow/plans",
        json={
            "request_text": "Prepare a release with rollback controls.",
            "requester_role": "release lead",
        },
    ).json()["workflow_id"]
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
        f"/workflow/plans/{workflow_id}/evidence/answer",
        json={"query": "rollback owner error threshold", "top_k": 3, "max_claims": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy"] == "lexical"
    assert payload["status"] == "grounded"
    assert payload["query_term_coverage"] == 1.0
    assert len(payload["claims"]) == 2
    assert all(claim["evidence_id"] == uploaded["evidence_id"] for claim in payload["claims"])
    assert all(claim["citation_id"] == uploaded["citation_id"] for claim in payload["claims"])

    hybrid_response = client.post(
        f"/workflow/plans/{workflow_id}/evidence/answer",
        json={
            "query": "Who is accountable for the backout?",
            "strategy": "hybrid",
        },
    )
    assert hybrid_response.status_code == 200
    assert hybrid_response.json()["strategy"] == "hybrid"
    assert hybrid_response.json()["status"] == "grounded"

    abstention_response = client.post(
        f"/workflow/plans/{workflow_id}/evidence/answer",
        json={
            "query": "Who authorized the emergency rollback?",
            "strategy": "hybrid",
        },
    )
    abstention = abstention_response.json()
    assert abstention["status"] == "insufficient_evidence"
    assert abstention["required_terms"] == ["approval", "rollback"]
    assert "approval + rollback" in abstention["answer"]


def test_grounding_baseline_meets_minimum_quality() -> None:
    results = evaluate_grounded_answers(
        load_and_validate_dataset(DEFAULT_DATASET),
        runs_per_case=2,
    )

    assert results["quality"]["grounding_behavior_accuracy"] == 1.0
    assert results["quality"]["citation_correctness"] == 1.0
    assert results["quality"]["citation_coverage"] == 1.0
    assert results["quality"]["expected_source_precision"] == 1.0
    assert results["quality"]["unsupported_claim_rate"] == 0.0


def test_challenge_grounding_filters_lower_confidence_distractors() -> None:
    results = evaluate_grounded_answers(
        load_and_validate_dataset(CHALLENGE_DATASET),
        runs_per_case=1,
        retriever=HybridEvidenceRetriever(),
        dataset_name="workflow_evidence_challenge_v1",
    )

    assert results["quality"]["grounding_behavior_accuracy"] == 1.0
    assert results["quality"]["citation_correctness"] == 1.0
    assert results["quality"]["unsupported_claim_rate"] == 0.0
    assert results["quality"]["expected_source_precision"] == 1.0
    assert results["quality"]["expected_source_recall"] == 1.0
    access_case = next(
        case
        for case in results["cases"]
        if case["case_id"] == "access-paraphrase-008"
    )
    assert access_case["cited_sources"] == ["access-policy"]
    assert access_case["context_policy"] == "strong_only"
    assert access_case["excluded_result_count"] == 2
    absence = next(
        case
        for case in results["cases"]
        if case["case_id"] == "absence-distractors-012"
    )
    assert absence["actual_status"] == "insufficient_evidence"


def test_combined_grounding_preserves_precision_and_restores_recall() -> None:
    records = load_and_validate_dataset(DEFAULT_DATASET)
    records.extend(load_and_validate_dataset(CHALLENGE_DATASET))
    results = evaluate_grounded_answers(
        records,
        runs_per_case=1,
        retriever=HybridEvidenceRetriever(),
        dataset_name="workflow_evidence_combined_v1",
    )

    assert results["quality"]["expected_source_precision"] == 1.0
    assert results["quality"]["expected_source_recall"] == 1.0
    release_case = next(
        case
        for case in results["cases"]
        if case["case_id"] == "release-grounded-001"
    )
    assert release_case["cited_sources"] == ["release-brief", "support-plan"]
    assert release_case["context_policy"] == "strong_plus_supporting"


def test_context_policy_adversarial_suite_blocks_false_friends() -> None:
    results = evaluate_grounded_answers(
        load_and_validate_dataset(CONTEXT_POLICY_DATASET),
        runs_per_case=1,
        retriever=HybridEvidenceRetriever(),
        dataset_name="workflow_evidence_context_policy_v1",
    )

    assert results["quality"]["grounding_behavior_accuracy"] == 1.0
    assert results["quality"]["expected_source_precision"] == 1.0
    assert results["quality"]["expected_source_recall"] == 1.0
    cases = {case["case_id"]: case for case in results["cases"]}
    assert cases["support-coverage-completion-013"]["context_policy"] == (
        "strong_plus_supporting"
    )
    assert cases["test-coverage-false-friend-014"]["cited_sources"] == [
        "release-runbook"
    ]
    assert cases["support-coverage-query-017"]["context_policy"] == (
        "supporting_only"
    )
    assert cases["coverage-compound-abstention-018"]["actual_status"] == (
        "insufficient_evidence"
    )
