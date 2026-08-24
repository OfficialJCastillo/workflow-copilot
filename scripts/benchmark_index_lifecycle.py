import argparse
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
import json
import platform
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from threading import Event
from time import perf_counter
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.hybrid_retrieval import HybridEvidenceRetriever
from app.services.persistent_hybrid_retrieval import (
    IndexCleanup,
    IndexPreparation,
    PersistentHybridEvidenceRetriever,
)
from app.services.retrieval import SearchDocument
from scripts.evaluate_retrieval import _percentile


DEFAULT_RESULTS = (
    PROJECT_ROOT
    / "evaluation"
    / "results"
    / "index_lifecycle_concurrency_v1.json"
)


def _latency_summary(values: list[float]) -> dict[str, float | int]:
    return {
        "sample_count": len(values),
        "total": round(sum(values), 4),
        "p50": round(_percentile(values, 0.50), 4),
        "p95": round(_percentile(values, 0.95), 4),
        "maximum": round(max(values), 4) if values else 0.0,
    }


def _synthetic_documents(
    namespace_index: int,
    *,
    document_count: int,
    words_per_document: int,
    revision: int,
) -> list[SearchDocument]:
    documents = []
    for document_index in range(document_count):
        vocabulary = (
            "release",
            "rollback",
            "owner",
            "platform",
            "verification",
            "support",
            "coverage",
            "approval",
            "security",
            "readiness",
            f"namespace{namespace_index:03d}",
            f"document{document_index:03d}",
            f"revision{revision:02d}",
        )
        content = " ".join(
            vocabulary[position % len(vocabulary)]
            for position in range(words_per_document)
        )
        source_id = f"ns-{namespace_index:03d}-doc-{document_index:03d}"
        documents.append(
            SearchDocument(
                source_id=source_id,
                citation_id=f"SRC-{namespace_index:03d}-{document_index:03d}",
                filename=f"workflow-{namespace_index:03d}-{document_index:03d}.txt",
                content=content,
            )
        )
    return documents


def _run_concurrent_phase(
    operations: list[Callable[[], Any]],
    *,
    workers: int,
) -> tuple[dict[str, object], list[Any]]:
    start_event = Event()

    def invoke(operation: Callable[[], Any]) -> tuple[float, Any, str | None]:
        start_event.wait()
        started = perf_counter()
        try:
            value = operation()
            error_type = None
        except Exception as error:  # benchmark captures operational failures
            value = None
            error_type = type(error).__name__
        return (perf_counter() - started) * 1_000, value, error_type

    wall_started = perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(invoke, operation) for operation in operations]
        start_event.set()
        attempts = [future.result() for future in futures]
    wall_clock_ms = (perf_counter() - wall_started) * 1_000

    errors = Counter(
        error_type
        for _, _, error_type in attempts
        if error_type is not None
    )
    successful_values = [
        value
        for _, value, error_type in attempts
        if error_type is None
    ]
    success_count = len(successful_values)
    return (
        {
            "requested_operations": len(operations),
            "success_count": success_count,
            "error_count": sum(errors.values()),
            "error_types": dict(sorted(errors.items())),
            "worker_count": workers,
            "wall_clock_ms": round(wall_clock_ms, 4),
            "throughput_operations_per_second": round(
                success_count / max(wall_clock_ms / 1_000, 0.000001),
                4,
            ),
            "operation_latency_ms": _latency_summary(
                [latency for latency, _, _ in attempts]
            ),
        },
        successful_values,
    )


def benchmark_index_lifecycle(
    *,
    index_path: Path,
    namespace_count: int = 12,
    documents_per_namespace: int = 32,
    words_per_document: int = 480,
    workers: int = 4,
) -> dict[str, object]:
    if namespace_count < 1:
        raise ValueError("namespace_count must be positive.")
    if documents_per_namespace < 2:
        raise ValueError("documents_per_namespace must be at least 2.")
    if words_per_document < 20:
        raise ValueError("words_per_document must be at least 20.")
    if workers < 1:
        raise ValueError("workers must be positive.")
    if index_path.exists():
        raise ValueError("index_path must not already exist.")

    initial_corpora = [
        _synthetic_documents(
            namespace_index,
            document_count=documents_per_namespace,
            words_per_document=words_per_document,
            revision=1,
        )
        for namespace_index in range(namespace_count)
    ]
    refreshed_corpora = [
        _synthetic_documents(
            namespace_index,
            document_count=documents_per_namespace,
            words_per_document=words_per_document,
            revision=2,
        )
        for namespace_index in range(namespace_count)
    ]
    documents_removed_per_namespace = max(1, documents_per_namespace // 4)
    retained_documents_per_namespace = (
        documents_per_namespace - documents_removed_per_namespace
    )
    deletion_corpora = [
        documents[:retained_documents_per_namespace]
        for documents in refreshed_corpora
    ]
    namespaces = [
        f"workflow:benchmark-{namespace_index:03d}"
        for namespace_index in range(namespace_count)
    ]
    total_source_bytes = sum(
        len(document.content.encode("utf-8"))
        for corpus in initial_corpora
        for document in corpus
    )
    chunks_per_namespace = len(
        HybridEvidenceRetriever().chunk_documents(initial_corpora[0])
    )

    retriever = PersistentHybridEvidenceRetriever(index_path=index_path)
    initial_phase, _ = _run_concurrent_phase(
        [
            lambda documents=documents, namespace=namespace: retriever.prepare_documents(
                documents,
                namespace=namespace,
            )
            for namespace, documents in zip(namespaces, initial_corpora, strict=True)
        ],
        workers=min(workers, namespace_count),
    )
    initial_state = {
        "indexed_namespace_count": retriever.indexed_namespace_count,
        "indexed_corpus_count": retriever.indexed_corpus_count,
        "indexed_chunk_count": retriever.indexed_chunk_count,
        "index_size_bytes": retriever.index_size_bytes,
    }

    refresh_phase, refresh_values = _run_concurrent_phase(
        [
            lambda documents=documents, namespace=namespace: retriever.prepare_documents(
                documents,
                namespace=namespace,
            )
            for namespace, documents in zip(namespaces, refreshed_corpora, strict=True)
        ],
        workers=min(workers, namespace_count),
    )
    refresh_state = {
        "indexed_namespace_count": retriever.indexed_namespace_count,
        "indexed_corpus_count": retriever.indexed_corpus_count,
        "indexed_chunk_count": retriever.indexed_chunk_count,
        "index_size_bytes": retriever.index_size_bytes,
        "removed_corpus_count": sum(
            preparation.removed_corpus_count
            for preparation in refresh_values
            if isinstance(preparation, IndexPreparation)
        ),
    }

    delete_refresh_phase, delete_refresh_values = _run_concurrent_phase(
        [
            lambda documents=documents, namespace=namespace: retriever.prepare_documents(
                documents,
                namespace=namespace,
            )
            for namespace, documents in zip(namespaces, deletion_corpora, strict=True)
        ],
        workers=min(workers, namespace_count),
    )
    delete_refresh_state = {
        "indexed_namespace_count": retriever.indexed_namespace_count,
        "indexed_corpus_count": retriever.indexed_corpus_count,
        "indexed_chunk_count": retriever.indexed_chunk_count,
        "index_size_bytes": retriever.index_size_bytes,
        "removed_corpus_count": sum(
            preparation.removed_corpus_count
            for preparation in delete_refresh_values
            if isinstance(preparation, IndexPreparation)
        ),
    }

    restarted = PersistentHybridEvidenceRetriever(index_path=index_path)
    restart_phase, restart_values = _run_concurrent_phase(
        [
            lambda documents=documents: restarted.chunk_documents(documents)
            for documents in deletion_corpora
        ],
        workers=min(workers, namespace_count),
    )
    restart_phase["loaded_chunk_count"] = sum(
        len(chunks)
        for chunks in restart_values
        if isinstance(chunks, list)
    )

    size_before_clear = retriever.index_size_bytes
    clear_phase, clear_values = _run_concurrent_phase(
        [
            lambda namespace=namespace: retriever.clear_namespace(namespace)
            for namespace in namespaces
        ],
        workers=min(workers, namespace_count),
    )
    clear_state = {
        "indexed_namespace_count": retriever.indexed_namespace_count,
        "indexed_corpus_count": retriever.indexed_corpus_count,
        "indexed_chunk_count": retriever.indexed_chunk_count,
        "index_size_bytes": retriever.index_size_bytes,
        "removed_namespace_count": sum(
            cleanup.removed_namespace_count
            for cleanup in clear_values
            if isinstance(cleanup, IndexCleanup)
        ),
        "removed_corpus_count": sum(
            cleanup.removed_corpus_count
            for cleanup in clear_values
            if isinstance(cleanup, IndexCleanup)
        ),
    }

    compaction_started = perf_counter()
    compaction = retriever.compact()
    compaction_latency_ms = (perf_counter() - compaction_started) * 1_000
    compaction_phase = {
        "operation_latency_ms": round(compaction_latency_ms, 4),
        "before_bytes": compaction.before_bytes,
        "after_bytes": compaction.after_bytes,
        "reclaimed_bytes": compaction.reclaimed_bytes,
    }

    expected_chunk_count = namespace_count * chunks_per_namespace
    retained_chunks_per_namespace = len(
        HybridEvidenceRetriever().chunk_documents(deletion_corpora[0])
    )
    expected_retained_chunk_count = (
        namespace_count * retained_chunks_per_namespace
    )
    invariants = {
        "initial_build_completed_without_errors": initial_phase["error_count"] == 0,
        "initial_namespace_count_matches": (
            initial_state["indexed_namespace_count"] == namespace_count
        ),
        "initial_corpus_count_matches": (
            initial_state["indexed_corpus_count"] == namespace_count
        ),
        "initial_chunk_count_matches": (
            initial_state["indexed_chunk_count"] == expected_chunk_count
        ),
        "refresh_completed_without_errors": refresh_phase["error_count"] == 0,
        "refresh_namespace_count_matches": (
            refresh_state["indexed_namespace_count"] == namespace_count
        ),
        "refresh_pruned_previous_corpora": (
            refresh_state["removed_corpus_count"] == namespace_count
            and refresh_state["indexed_corpus_count"] == namespace_count
        ),
        "delete_refresh_completed_without_errors": (
            delete_refresh_phase["error_count"] == 0
        ),
        "delete_refresh_pruned_previous_corpora": (
            delete_refresh_state["removed_corpus_count"] == namespace_count
            and delete_refresh_state["indexed_corpus_count"] == namespace_count
        ),
        "delete_refresh_removed_expected_chunks": (
            delete_refresh_state["indexed_chunk_count"]
            == expected_retained_chunk_count
        ),
        "restart_load_completed_without_errors": restart_phase["error_count"] == 0,
        "restart_loaded_all_chunks": (
            restart_phase["loaded_chunk_count"] == expected_retained_chunk_count
        ),
        "clear_completed_without_errors": clear_phase["error_count"] == 0,
        "clear_removed_all_namespaces": (
            clear_state["removed_namespace_count"] == namespace_count
            and clear_state["indexed_namespace_count"] == 0
        ),
        "clear_removed_all_corpora_and_chunks": (
            clear_state["removed_corpus_count"] == namespace_count
            and clear_state["indexed_corpus_count"] == 0
            and clear_state["indexed_chunk_count"] == 0
        ),
        "compaction_did_not_grow_index": (
            compaction.after_bytes <= compaction.before_bytes
        ),
    }

    return {
        "schema_version": 1,
        "suite": "sqlite_index_lifecycle_concurrency_v1",
        "workload": {
            "namespace_count": namespace_count,
            "documents_per_namespace": documents_per_namespace,
            "total_documents": namespace_count * documents_per_namespace,
            "documents_removed_per_namespace": documents_removed_per_namespace,
            "retained_documents_per_namespace": retained_documents_per_namespace,
            "words_per_document": words_per_document,
            "total_source_bytes": total_source_bytes,
            "chunks_per_namespace": chunks_per_namespace,
            "expected_total_chunks": expected_chunk_count,
            "expected_chunks_after_delete": expected_retained_chunk_count,
            "worker_count": min(workers, namespace_count),
        },
        "methodology": {
            "corpus": "deterministic_synthetic",
            "initial_revision": 1,
            "refresh_revision": 2,
            "chunk_words": retriever.chunk_words,
            "overlap_words": retriever.overlap_words,
            "compaction_policy": "after_concurrent_writers_quiesce",
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "sqlite": sqlite3.sqlite_version,
        },
        "phases": {
            "concurrent_initial_build": initial_phase,
            "concurrent_refresh": refresh_phase,
            "concurrent_delete_refresh": delete_refresh_phase,
            "concurrent_restart_load": restart_phase,
            "concurrent_clear": clear_phase,
            "exclusive_compaction": compaction_phase,
        },
        "states": {
            "after_initial_build": initial_state,
            "after_refresh": refresh_state,
            "after_delete_refresh": delete_refresh_state,
            "after_clear": clear_state,
            "size_before_clear_bytes": size_before_clear,
        },
        "invariants": invariants,
        "all_invariants_passed": all(invariants.values()),
        "limitations": [
            "Synthetic text does not represent production document diversity.",
            "Thread concurrency in one Python process does not model multiple hosts.",
            "SQLite serializes writers; throughput is not a remote-database claim.",
            "VACUUM runs after concurrent writers finish because it requires exclusive access.",
            "Latency is environment-specific and is not asserted in CI.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark concurrent SQLite hybrid-index build, refresh, reload, "
            "cleanup, and compaction."
        )
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--index-path", type=Path)
    parser.add_argument("--namespaces", type=int, default=12)
    parser.add_argument("--documents-per-namespace", type=int, default=32)
    parser.add_argument("--words-per-document", type=int, default=480)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    if args.index_path:
        results = benchmark_index_lifecycle(
            index_path=args.index_path,
            namespace_count=args.namespaces,
            documents_per_namespace=args.documents_per_namespace,
            words_per_document=args.words_per_document,
            workers=args.workers,
        )
    else:
        with TemporaryDirectory(prefix="workflow-index-lifecycle-") as directory:
            results = benchmark_index_lifecycle(
                index_path=Path(directory) / "hybrid-index.db",
                namespace_count=args.namespaces,
                documents_per_namespace=args.documents_per_namespace,
                words_per_document=args.words_per_document,
                workers=args.workers,
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        f"{json.dumps(results, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    refresh = results["phases"]["concurrent_refresh"]
    delete_refresh = results["phases"]["concurrent_delete_refresh"]
    clear = results["phases"]["concurrent_clear"]
    compaction = results["phases"]["exclusive_compaction"]
    print(
        f"Benchmarked {results['workload']['total_documents']} documents with "
        f"{results['workload']['worker_count']} workers: "
        f"refresh P95={refresh['operation_latency_ms']['p95']:.4f} ms, "
        f"delete-refresh P95={delete_refresh['operation_latency_ms']['p95']:.4f} ms, "
        f"clear P95={clear['operation_latency_ms']['p95']:.4f} ms, "
        f"compaction={compaction['operation_latency_ms']:.4f} ms, "
        f"invariants={'pass' if results['all_invariants_passed'] else 'fail'}."
    )
    if not results["all_invariants_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
