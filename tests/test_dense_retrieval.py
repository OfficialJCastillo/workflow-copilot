from collections.abc import Sequence

from app.services.dense_retrieval import DenseEvidenceRetriever
from app.services.retrieval import SearchDocument


class SemanticStubEncoder:
    model_name = "semantic-stub"
    dimension = 3

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        vectors = []
        for text in texts:
            normalized = text.casefold()
            if any(term in normalized for term in ("accountable", "backout", "rollback owner")):
                vectors.append((1.0, 0.0, 0.0))
            elif any(term in normalized for term in ("calendar", "presentation")):
                vectors.append((0.0, 1.0, 0.0))
            else:
                vectors.append((0.0, 0.0, 1.0))
        return vectors


def _documents() -> list[SearchDocument]:
    return [
        SearchDocument(
            source_id="runbook",
            citation_id="SRC-RUNBOOK",
            filename="runbook.txt",
            content="Rollback owner is Platform SRE.",
        ),
        SearchDocument(
            source_id="calendar",
            citation_id="SRC-CALENDAR",
            filename="calendar.txt",
            content="The presentation calendar lists meeting dates.",
        ),
    ]


def test_dense_retriever_ranks_semantic_match_and_reuses_embeddings() -> None:
    retriever = DenseEvidenceRetriever(
        SemanticStubEncoder(),
        minimum_similarity=0.5,
    )

    initial = retriever.search(
        query="Who is accountable for the backout?",
        documents=_documents(),
        top_k=2,
    )
    repeated = retriever.search(
        query="Who is accountable for the backout?",
        documents=list(reversed(_documents())),
        top_k=2,
    )

    assert [result.source_id for result in initial.results] == ["runbook"]
    assert repeated.results == initial.results
    assert retriever.corpus_cache_misses == 1
    assert retriever.corpus_cache_hits == 1
    assert retriever.query_cache_misses == 1
    assert retriever.query_cache_hits == 1


def test_dense_retriever_threshold_abstains_from_unrelated_sources() -> None:
    retriever = DenseEvidenceRetriever(
        SemanticStubEncoder(),
        minimum_similarity=0.5,
    )

    result = retriever.search(
        query="What insurance must the supplier carry?",
        documents=_documents(),
    )

    assert result.results == ()
    assert result.total_chunks == 2


def test_dense_retriever_can_measure_fresh_query_embeddings() -> None:
    retriever = DenseEvidenceRetriever(
        SemanticStubEncoder(),
        minimum_similarity=0.5,
        cache_queries=False,
    )

    for _ in range(2):
        retriever.search(
            query="Who is accountable for the backout?",
            documents=_documents(),
        )

    assert retriever.query_cache_hits == 0
    assert retriever.query_cache_misses == 2
