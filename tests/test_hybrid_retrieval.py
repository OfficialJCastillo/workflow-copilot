from pathlib import Path

from app.services.hybrid_retrieval import HybridEvidenceRetriever
from app.services.retrieval import EvidenceRetriever
from app.services.retrieval import SearchDocument
from scripts.compare_retrieval_strategies import compare_strategies
from scripts.validate_evaluation_dataset import DEFAULT_DATASET
from scripts.validate_evaluation_dataset import load_and_validate_dataset


CHALLENGE_DATASET = (
    Path(__file__).resolve().parents[1]
    / "evaluation"
    / "datasets"
    / "workflow_evidence_challenge_v1.jsonl"
)


def test_hybrid_retriever_resolves_operations_paraphrases() -> None:
    documents = [
        SearchDocument(
            source_id="recovery-procedure",
            citation_id="SRC-RECOVERY",
            filename="recovery-procedure.txt",
            content=(
                "Rollback owner is Platform SRE. "
                "Revert when error rate exceeds three percent."
            ),
        ),
        SearchDocument(
            source_id="launch-calendar",
            citation_id="SRC-CALENDAR",
            filename="launch-calendar.txt",
            content="The rollout launch calendar lists presentation dates.",
        ),
    ]
    query = "Who is accountable for the backout if the rollout deteriorates?"

    lexical = EvidenceRetriever().search(query=query, documents=documents, top_k=1)
    hybrid = HybridEvidenceRetriever().search(query=query, documents=documents, top_k=1)

    assert lexical.results[0].source_id == "launch-calendar"
    assert hybrid.results[0].source_id == "recovery-procedure"
    assert {"owner", "rollback", "error"} <= set(hybrid.results[0].matched_terms)


def test_hybrid_retriever_abstains_when_compound_intent_is_distributed() -> None:
    result = HybridEvidenceRetriever().search(
        query="Who authorized the emergency database backout?",
        documents=[
            SearchDocument(
                source_id="contacts",
                citation_id="SRC-CONTACTS",
                filename="contacts.txt",
                content="Emergency regional telephone numbers.",
            ),
            SearchDocument(
                source_id="training",
                citation_id="SRC-TRAINING",
                filename="training.txt",
                content="Backout training dates are published quarterly.",
            ),
        ],
    )

    assert result.results == ()
    assert result.abstention_reason == "compound_intent_not_supported"
    assert result.required_terms == ("approval", "rollback")


def test_pairwise_reranker_prioritizes_core_concept_coverage() -> None:
    result = HybridEvidenceRetriever().search(
        query="Which entitlements require signoff before the contractor begins?",
        documents=[
            SearchDocument(
                source_id="access-policy",
                citation_id="SRC-ACCESS",
                filename="access-policy.txt",
                content="Manager approval is mandatory for production access prior to onboarding.",
            ),
            SearchDocument(
                source_id="safety-training",
                citation_id="SRC-SAFETY",
                filename="safety-training.txt",
                content="A facilities signoff is required before the contractor enters the laboratory.",
            ),
        ],
        top_k=2,
    )

    assert [item.source_id for item in result.results] == [
        "access-policy",
        "safety-training",
    ]
    assert result.results[0].relevance_label == "strong"
    assert result.results[0].core_matches == ("access", "approval")
    assert result.results[1].relevance_label == "supporting"


def test_support_coverage_phrase_does_not_promote_generic_coverage() -> None:
    result = HybridEvidenceRetriever().search(
        query="Confirm customer API readiness.",
        documents=[
            SearchDocument(
                source_id="support-roster",
                citation_id="SRC-SUPPORT",
                filename="support-roster.txt",
                content="Customer Support coverage is confirmed for Thursday.",
            ),
            SearchDocument(
                source_id="test-report",
                citation_id="SRC-TEST",
                filename="test-report.txt",
                content="Customer API unit test coverage is 92 percent.",
            ),
        ],
        top_k=2,
    )

    assert [item.source_id for item in result.results] == [
        "support-roster",
        "test-report",
    ]
    assert result.results[0].core_matches == ("readiness",)
    assert result.results[0].relevance_label == "supporting"
    assert result.results[1].core_matches == ()
    assert result.results[1].relevance_label == "weak"


def test_comparison_reports_hybrid_lift_and_calibrated_abstention() -> None:
    results = compare_strategies(
        load_and_validate_dataset(DEFAULT_DATASET),
        load_and_validate_dataset(CHALLENGE_DATASET),
        runs_per_case=1,
    )

    challenge = results["slices"]["challenge"]
    assert challenge["lexical"]["quality"]["source_recall_at_k"] == 0.1
    assert challenge["hybrid"]["quality"]["source_recall_at_k"] == 1.0
    assert challenge["hybrid"]["quality"]["mean_reciprocal_rank"] == 1.0
    assert challenge["hybrid"]["quality"]["evidence_absence_accuracy"] == 1.0
    assert challenge["lexical"]["quality"]["evidence_absence_accuracy"] == 0.0
    assert results["combined_quality_delta_hybrid_minus_lexical"][
        "source_recall_at_k"
    ] > 0
