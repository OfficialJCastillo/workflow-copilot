from collections.abc import Sequence

from app.services.fusion_retrieval import FusionEvidenceRetriever
from app.services.retrieval import SearchDocument


class FusionStubEncoder:
    model_name = "fusion-stub"
    dimension = 3

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        vectors = []
        for text in texts:
            normalized = text.casefold()
            if any(term in normalized for term in ("backout", "rollback owner")):
                vectors.append((1.0, 0.0, 0.0))
            elif "approval" in normalized or "authorization" in normalized:
                vectors.append((0.0, 1.0, 0.0))
            else:
                vectors.append((0.0, 0.0, 1.0))
        return vectors


def _document(source_id: str, content: str) -> SearchDocument:
    return SearchDocument(
        source_id=source_id,
        citation_id=f"SRC-{source_id.upper()}",
        filename=f"{source_id}.txt",
        content=content,
    )


def test_fusion_ranks_semantic_evidence() -> None:
    retriever = FusionEvidenceRetriever(
        FusionStubEncoder(),
        minimum_dense_similarity=0.2,
    )

    result = retriever.search(
        query="Who is accountable for the backout?",
        documents=[
            _document("runbook", "Rollback owner is Platform SRE."),
            _document("calendar", "The meeting calendar lists presentation dates."),
        ],
    )

    assert result.results[0].source_id == "runbook"


def test_fusion_requires_explicit_authorization_support() -> None:
    retriever = FusionEvidenceRetriever(FusionStubEncoder())

    result = retriever.search(
        query="Which executive approved the residency exception?",
        documents=[
            _document(
                "policy",
                "Customer data must remain local unless an exception is granted.",
            ),
            _document("directory", "The executive directory lists assistants."),
        ],
    )

    assert result.results == ()
    assert result.abstention_reason == "answer_slot_not_supported"
    assert result.required_terms == ("approval",)


def test_fusion_requires_completed_outcome_support() -> None:
    retriever = FusionEvidenceRetriever(FusionStubEncoder())

    result = retriever.search(
        query="What was the final outcome of the penetration test?",
        documents=[
            _document("schedule", "The penetration test is scheduled next week."),
            _document("template", "The finding template has empty severity fields."),
        ],
    )

    assert result.results == ()
    assert result.abstention_reason == "answer_slot_not_supported"
    assert result.required_terms == ("outcome_status",)


def test_fusion_accepts_supported_authorization_actor() -> None:
    retriever = FusionEvidenceRetriever(FusionStubEncoder())

    result = retriever.search(
        query="Who must sign off on the purchase?",
        documents=[
            _document(
                "authority",
                "Written authorization from the Vice President of Finance is required.",
            )
        ],
    )

    assert [item.source_id for item in result.results] == ["authority"]
    assert result.required_terms == ("approval",)
