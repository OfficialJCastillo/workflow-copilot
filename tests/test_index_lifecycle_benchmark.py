from pathlib import Path

import pytest

from scripts.benchmark_index_lifecycle import benchmark_index_lifecycle


def test_concurrent_index_lifecycle_preserves_cleanup_invariants(
    tmp_path: Path,
) -> None:
    results = benchmark_index_lifecycle(
        index_path=tmp_path / "lifecycle-index.db",
        namespace_count=4,
        documents_per_namespace=3,
        words_per_document=120,
        workers=2,
    )

    assert results["schema_version"] == 1
    assert results["workload"] == {
        "namespace_count": 4,
        "documents_per_namespace": 3,
        "total_documents": 12,
        "documents_removed_per_namespace": 1,
        "retained_documents_per_namespace": 2,
        "words_per_document": 120,
        "total_source_bytes": results["workload"]["total_source_bytes"],
        "chunks_per_namespace": 3,
        "expected_total_chunks": 12,
        "expected_chunks_after_delete": 8,
        "worker_count": 2,
    }
    assert results["all_invariants_passed"] is True
    assert all(results["invariants"].values())
    for phase_name in (
        "concurrent_initial_build",
        "concurrent_refresh",
        "concurrent_delete_refresh",
        "concurrent_restart_load",
        "concurrent_clear",
    ):
        assert results["phases"][phase_name]["error_count"] == 0
        assert results["phases"][phase_name]["success_count"] == 4

    assert results["states"]["after_initial_build"]["indexed_chunk_count"] == 12
    assert results["states"]["after_refresh"]["removed_corpus_count"] == 4
    assert results["states"]["after_delete_refresh"]["removed_corpus_count"] == 4
    assert results["states"]["after_delete_refresh"]["indexed_chunk_count"] == 8
    assert results["states"]["after_clear"]["indexed_namespace_count"] == 0
    assert results["states"]["after_clear"]["indexed_corpus_count"] == 0
    assert results["states"]["after_clear"]["indexed_chunk_count"] == 0
    assert (
        results["phases"]["exclusive_compaction"]["after_bytes"]
        <= results["phases"]["exclusive_compaction"]["before_bytes"]
    )


@pytest.mark.parametrize(
    "invalid",
    (
        {"namespace_count": 0},
        {"documents_per_namespace": 1},
        {"words_per_document": 19},
        {"workers": 0},
    ),
)
def test_index_lifecycle_benchmark_validates_workload_parameters(
    tmp_path: Path,
    invalid: dict[str, int],
) -> None:
    with pytest.raises(ValueError):
        benchmark_index_lifecycle(
            index_path=tmp_path / "invalid-index.db",
            **invalid,
        )


def test_index_lifecycle_benchmark_rejects_an_existing_index(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "existing-index.db"
    index_path.touch()

    with pytest.raises(ValueError, match="must not already exist"):
        benchmark_index_lifecycle(index_path=index_path)
