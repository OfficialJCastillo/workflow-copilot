from pathlib import Path

from app.services.persistent_hybrid_retrieval import (
    PersistentHybridEvidenceRetriever,
)
from app.services.retrieval import SearchDocument
from scripts.compare_persisted_hybrid import DEFAULT_DATASETS
from scripts.compare_persisted_hybrid import compare_persisted_hybrid
from scripts.validate_evaluation_dataset import load_and_validate_dataset


def _documents() -> list[SearchDocument]:
    return [
        SearchDocument(
            source_id="release-runbook",
            citation_id="SRC-RUNBOOK",
            filename="release-runbook.txt",
            content=(
                "Rollback owner is Platform SRE. "
                "Revert when errors exceed three percent."
            ),
        ),
        SearchDocument(
            source_id="launch-calendar",
            citation_id="SRC-CALENDAR",
            filename="launch-calendar.txt",
            content="The launch calendar lists presentation dates.",
        ),
    ]


def test_persisted_hybrid_index_reuses_chunks_after_restart(tmp_path: Path) -> None:
    index_path = tmp_path / "hybrid-index.db"
    first = PersistentHybridEvidenceRetriever(index_path=index_path)
    initial = first.search(
        query="Who owns the backout when failures increase?",
        documents=_documents(),
        top_k=2,
    )

    assert initial.results[0].source_id == "release-runbook"
    assert first.cache_misses == 1
    assert first.cache_hits == 0
    assert first.indexed_corpus_count == 1
    assert first.index_size_bytes > 0

    repeated = first.search(
        query="Who owns the backout when failures increase?",
        documents=list(reversed(_documents())),
        top_k=2,
    )
    assert repeated.results == initial.results
    assert first.memory_cache_hits == 1

    restarted = PersistentHybridEvidenceRetriever(index_path=index_path)
    restored = restarted.search(
        query="Who owns the backout when failures increase?",
        documents=_documents(),
        top_k=2,
    )
    assert restored.results == initial.results
    assert restarted.disk_cache_hits == 1
    assert restarted.cache_misses == 0


def test_persisted_hybrid_index_invalidates_changed_corpus(tmp_path: Path) -> None:
    index_path = tmp_path / "hybrid-index.db"
    retriever = PersistentHybridEvidenceRetriever(index_path=index_path)
    retriever.search(query="rollback owner", documents=_documents())
    changed_documents = _documents()
    changed_documents[0] = SearchDocument(
        source_id="release-runbook",
        citation_id="SRC-RUNBOOK",
        filename="release-runbook.txt",
        content="Rollback owner is the Release Manager.",
    )

    changed = retriever.search(
        query="rollback owner",
        documents=changed_documents,
    )

    assert changed.results[0].content == "Rollback owner is the Release Manager."
    assert retriever.cache_misses == 2
    assert retriever.indexed_corpus_count == 2


def test_namespaced_preparation_prunes_only_unreferenced_corpora(tmp_path: Path) -> None:
    index_path = tmp_path / "hybrid-index.db"
    retriever = PersistentHybridEvidenceRetriever(index_path=index_path)
    first = retriever.prepare_documents(_documents(), namespace="workflow-a")
    shared = retriever.prepare_documents(_documents(), namespace="workflow-b")
    changed_documents = _documents()
    changed_documents.append(
        SearchDocument(
            source_id="support-plan",
            citation_id="SRC-SUPPORT",
            filename="support-plan.txt",
            content="Customer Support coverage begins at 20:30 UTC.",
        )
    )

    changed_a = retriever.prepare_documents(
        changed_documents,
        namespace="workflow-a",
    )
    changed_b = retriever.prepare_documents(
        changed_documents,
        namespace="workflow-b",
    )

    assert first.cache_status == "built"
    assert shared.cache_status == "memory_hit"
    assert changed_a.removed_corpus_count == 0
    assert changed_b.removed_corpus_count == 1
    assert retriever.indexed_namespace_count == 2
    assert retriever.indexed_corpus_count == 1
    assert retriever.indexed_chunk_count == 3


def test_namespace_cleanup_removes_orphaned_corpus_and_compacts_index(
    tmp_path: Path,
) -> None:
    retriever = PersistentHybridEvidenceRetriever(
        index_path=tmp_path / "hybrid-index.db"
    )
    retriever.prepare_documents(_documents(), namespace="workflow-a")

    cleanup = retriever.clear_namespace("workflow-a")
    compaction = retriever.compact()
    repeated_cleanup = retriever.clear_namespace("workflow-a")

    assert cleanup.removed_namespace_count == 1
    assert cleanup.removed_corpus_count == 1
    assert retriever.indexed_namespace_count == 0
    assert retriever.indexed_corpus_count == 0
    assert retriever.indexed_chunk_count == 0
    assert compaction.after_bytes <= compaction.before_bytes
    assert compaction.reclaimed_bytes == (
        compaction.before_bytes - compaction.after_bytes
    )
    assert retriever.compaction_count == 1
    assert retriever.last_compaction_reclaimed_bytes == compaction.reclaimed_bytes
    assert repeated_cleanup.removed_namespace_count == 0
    assert repeated_cleanup.removed_corpus_count == 0


def test_persisted_hybrid_comparison_preserves_quality(tmp_path: Path) -> None:
    records = [
        record
        for dataset_path in DEFAULT_DATASETS
        for record in load_and_validate_dataset(dataset_path)
    ]
    comparison = compare_persisted_hybrid(
        records,
        index_path=tmp_path / "comparison-index.db",
        runs_per_case=1,
    )

    assert comparison["case_count"] == 18
    assert comparison["quality_delta_persisted_minus_sparse"] == {
        "source_recall_at_k": 0.0,
        "mean_reciprocal_rank": 0.0,
        "evidence_absence_accuracy": 0.0,
    }
    assert comparison["results"]["persisted_hybrid"]["quality"] == {
        "source_recall_at_k": 1.0,
        "mean_reciprocal_rank": 1.0,
        "evidence_absence_accuracy": 1.0,
    }
    assert comparison["index"]["cold_builds"] == 18
    assert comparison["index"]["restart_disk_cache_hits"] == 18
    assert comparison["index"]["warm_memory_cache_hits"] == 18
