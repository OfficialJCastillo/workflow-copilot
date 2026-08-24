import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.hybrid_retrieval import HybridEvidenceRetriever
from app.services.persistent_hybrid_retrieval import (
    PersistentHybridEvidenceRetriever,
)
from app.services.retrieval import SearchDocument
from scripts.evaluate_retrieval import _percentile
from scripts.evaluate_retrieval import evaluate_records
from scripts.validate_evaluation_dataset import DEFAULT_DATASET
from scripts.validate_evaluation_dataset import load_and_validate_dataset


DEFAULT_DATASETS = (
    DEFAULT_DATASET,
    PROJECT_ROOT / "evaluation" / "datasets" / "workflow_evidence_challenge_v1.jsonl",
    PROJECT_ROOT
    / "evaluation"
    / "datasets"
    / "workflow_evidence_context_policy_v1.jsonl",
)
DEFAULT_RESULTS = (
    PROJECT_ROOT
    / "evaluation"
    / "results"
    / "persisted_hybrid_comparison_v1.json"
)


def _documents(record: dict[str, object]) -> list[SearchDocument]:
    return [
        SearchDocument(
            source_id=document["source_id"],
            citation_id=document["source_id"],
            filename=document["filename"],
            content=document["content"],
        )
        for document in record["evidence_documents"]
    ]


def _latency_summary(values: list[float]) -> dict[str, float | int]:
    return {
        "sample_count": len(values),
        "total": round(sum(values), 4),
        "p50": round(_percentile(values, 0.50), 4),
        "p95": round(_percentile(values, 0.95), 4),
        "maximum": round(max(values), 4) if values else 0.0,
    }


def compare_persisted_hybrid(
    records: list[dict[str, object]],
    *,
    index_path: Path,
    top_k: int = 3,
    runs_per_case: int = 50,
) -> dict[str, object]:
    sparse_result = evaluate_records(
        records,
        top_k=top_k,
        runs_per_case=runs_per_case,
        retriever=HybridEvidenceRetriever(),
        dataset_name="workflow_evidence_extended_v1",
    )

    builder = PersistentHybridEvidenceRetriever(index_path=index_path)
    for record in records:
        builder.chunk_documents(_documents(record))

    persisted = PersistentHybridEvidenceRetriever(index_path=index_path)
    for record in records:
        persisted.chunk_documents(_documents(record))
    persisted_result = evaluate_records(
        records,
        top_k=top_k,
        runs_per_case=runs_per_case,
        retriever=persisted,
        dataset_name="workflow_evidence_extended_v1",
    )

    sparse_quality = sparse_result["quality"]
    persisted_quality = persisted_result["quality"]
    return {
        "schema_version": 1,
        "suite": "workflow_evidence_extended_v1",
        "case_count": len(records),
        "top_k": top_k,
        "runs_per_case": runs_per_case,
        "quality_delta_persisted_minus_sparse": {
            metric: round(persisted_quality[metric] - sparse_quality[metric], 4)
            for metric in (
                "source_recall_at_k",
                "mean_reciprocal_rank",
                "evidence_absence_accuracy",
            )
        },
        "index": {
            "backend": "sqlite",
            "fingerprint": "sha256_corpus_and_chunk_configuration",
            "indexed_corpus_count": persisted.indexed_corpus_count,
            "indexed_chunk_count": persisted.indexed_chunk_count,
            "size_bytes": persisted.index_size_bytes,
            "cold_build_latency_ms": _latency_summary(builder.build_latencies_ms),
            "restart_disk_load_latency_ms": _latency_summary(
                persisted.disk_load_latencies_ms
            ),
            "cold_builds": builder.cache_misses,
            "restart_disk_cache_hits": persisted.disk_cache_hits,
            "warm_memory_cache_hits": persisted.memory_cache_hits,
        },
        "results": {
            "sparse_hybrid": sparse_result,
            "persisted_hybrid": persisted_result,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare sparse hybrid retrieval with a SQLite-persisted index."
    )
    parser.add_argument("--dataset", action="append", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--index-path", type=Path)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--runs-per-case", type=int, default=50)
    args = parser.parse_args()

    dataset_paths = tuple(args.dataset) if args.dataset else DEFAULT_DATASETS
    records = [
        record
        for dataset_path in dataset_paths
        for record in load_and_validate_dataset(dataset_path)
    ]
    if args.index_path:
        results = compare_persisted_hybrid(
            records,
            index_path=args.index_path,
            top_k=args.top_k,
            runs_per_case=args.runs_per_case,
        )
    else:
        with TemporaryDirectory(prefix="workflow-persisted-hybrid-") as directory:
            results = compare_persisted_hybrid(
                records,
                index_path=Path(directory) / "hybrid-index.db",
                top_k=args.top_k,
                runs_per_case=args.runs_per_case,
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        f"{json.dumps(results, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    sparse = results["results"]["sparse_hybrid"]
    persisted = results["results"]["persisted_hybrid"]
    print(
        f"Compared {results['case_count']} cases: "
        f"sparse P95={sparse['latency_ms']['p95']:.4f} ms, "
        f"persisted warm P95={persisted['latency_ms']['p95']:.4f} ms, "
        f"index={results['index']['size_bytes']} bytes."
    )


if __name__ == "__main__":
    main()
