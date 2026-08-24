import argparse
import json
from pathlib import Path
import sys
from time import perf_counter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.dense_retrieval import DEFAULT_DENSE_MODEL
from app.services.dense_retrieval import DenseEvidenceRetriever
from app.services.dense_retrieval import DenseTextEncoder
from app.services.dense_retrieval import FastEmbedTextEncoder
from app.services.hybrid_retrieval import HybridEvidenceRetriever
from app.services.retrieval import SearchDocument
from scripts.compare_persisted_hybrid import DEFAULT_DATASETS
from scripts.evaluate_retrieval import evaluate_records
from scripts.validate_evaluation_dataset import load_and_validate_dataset


DEFAULT_CANDIDATE_DATASET = (
    PROJECT_ROOT
    / "evaluation"
    / "datasets"
    / "workflow_evidence_dense_candidate_v1.jsonl"
)
DEFAULT_RESULTS = (
    PROJECT_ROOT
    / "evaluation"
    / "results"
    / "dense_retrieval_candidate_comparison_v1.json"
)
DEFAULT_THRESHOLDS = tuple(round(value / 100, 2) for value in range(20, 81, 5))


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


def _quality_objective(quality: dict[str, float | None]) -> float:
    values = [
        quality["source_recall_at_k"],
        quality["mean_reciprocal_rank"],
        quality["evidence_absence_accuracy"],
    ]
    available = [float(value) for value in values if value is not None]
    return sum(available) / len(available)


def _quality_delta(
    dense_quality: dict[str, float | None],
    sparse_quality: dict[str, float | None],
) -> dict[str, float | None]:
    delta: dict[str, float | None] = {}
    for metric in (
        "source_recall_at_k",
        "mean_reciprocal_rank",
        "evidence_absence_accuracy",
    ):
        dense_value = dense_quality[metric]
        sparse_value = sparse_quality[metric]
        delta[metric] = (
            round(float(dense_value) - float(sparse_value), 4)
            if dense_value is not None and sparse_value is not None
            else None
        )
    return delta


def _calibrate_threshold(
    records: list[dict[str, object]],
    *,
    encoder: DenseTextEncoder,
    thresholds: tuple[float, ...],
    top_k: int,
) -> tuple[float, list[dict[str, object]]]:
    if not records:
        raise ValueError("Dense threshold calibration requires development cases.")
    if not thresholds:
        raise ValueError("At least one dense threshold is required.")

    calibration: list[dict[str, object]] = []
    for threshold in sorted(set(thresholds)):
        retriever = DenseEvidenceRetriever(
            encoder,
            minimum_similarity=threshold,
            cache_queries=True,
        )
        result = evaluate_records(
            records,
            top_k=top_k,
            runs_per_case=1,
            retriever=retriever,
            dataset_name="workflow_evidence_dense_candidate_development_v1",
        )
        calibration.append(
            {
                "threshold": threshold,
                "objective": round(_quality_objective(result["quality"]), 4),
                "quality": result["quality"],
            }
        )

    # A lower threshold wins ties so equally accurate settings retain more evidence.
    selected = max(
        calibration,
        key=lambda row: (
            row["objective"],
            row["quality"]["source_recall_at_k"],
            row["quality"]["mean_reciprocal_rank"],
            -row["threshold"],
        ),
    )
    return float(selected["threshold"]), calibration


def _evaluate_slice(
    records: list[dict[str, object]],
    *,
    dataset_name: str,
    encoder: DenseTextEncoder,
    threshold: float,
    top_k: int,
    runs_per_case: int,
) -> dict[str, object]:
    dense = DenseEvidenceRetriever(
        encoder,
        minimum_similarity=threshold,
        cache_queries=False,
    )
    prewarm_started = perf_counter()
    chunk_count = 0
    for record in records:
        chunk_count += dense.prepare_documents(_documents(record)).chunk_count
    corpus_prewarm_ms = (perf_counter() - prewarm_started) * 1_000

    sparse_result = evaluate_records(
        records,
        top_k=top_k,
        runs_per_case=runs_per_case,
        retriever=HybridEvidenceRetriever(),
        dataset_name=dataset_name,
    )
    dense_result = evaluate_records(
        records,
        top_k=top_k,
        runs_per_case=runs_per_case,
        retriever=dense,
        dataset_name=dataset_name,
    )
    return {
        "quality_delta_dense_minus_sparse": _quality_delta(
            dense_result["quality"], sparse_result["quality"]
        ),
        "dense_corpus_prewarm": {
            "latency_ms": round(corpus_prewarm_ms, 4),
            "corpus_count": dense.corpus_cache_misses,
            "chunk_count": chunk_count,
        },
        "results": {
            "sparse_hybrid": sparse_result,
            "dense": dense_result,
        },
    }


def _label_summary(
    expanded_records: list[dict[str, object]],
    candidate_records: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "claim_status": "candidate_only_not_human_validated",
        "human_review_gate_passed": all(
            record.get("label_provenance") == "human_reviewed"
            and record.get("label_status") == "reviewed"
            for record in candidate_records
        ),
        "human_reviewed_case_count": sum(
            record.get("label_provenance") == "human_reviewed"
            and record.get("label_status") == "reviewed"
            for record in candidate_records
        ),
        "pending_human_review_case_count": sum(
            record.get("label_status") == "pending_human_review"
            for record in candidate_records
        ),
        "candidate_case_count": len(candidate_records),
        "legacy_synthetic_case_count": len(expanded_records) - len(candidate_records),
    }


def compare_dense_retrieval(
    existing_records: list[dict[str, object]],
    candidate_records: list[dict[str, object]],
    *,
    encoder: DenseTextEncoder,
    thresholds: tuple[float, ...] = DEFAULT_THRESHOLDS,
    top_k: int = 3,
    runs_per_case: int = 10,
) -> dict[str, object]:
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    if runs_per_case < 1:
        raise ValueError("runs_per_case must be at least 1.")
    development = [
        record for record in candidate_records if record.get("split") == "development"
    ]
    test = [record for record in candidate_records if record.get("split") == "test"]
    if not development or not test:
        raise ValueError("Candidate labels require non-empty development and test splits.")

    selected_threshold, calibration = _calibrate_threshold(
        development,
        encoder=encoder,
        thresholds=thresholds,
        top_k=top_k,
    )
    expanded = [*existing_records, *candidate_records]
    slice_records = {
        "candidate_development": development,
        "candidate_test": test,
        "candidate_combined": candidate_records,
        "expanded_synthetic": expanded,
    }
    slices = {
        name: _evaluate_slice(
            records,
            dataset_name=name,
            encoder=encoder,
            threshold=selected_threshold,
            top_k=top_k,
            runs_per_case=runs_per_case,
        )
        for name, records in slice_records.items()
    }
    label_summary = _label_summary(expanded, candidate_records)
    dense_model = {
        "name": encoder.model_name,
        "embedding_dimension": encoder.dimension,
        "runtime_dependency": "fastembed==0.8.0",
        "production_dependency": False,
    }
    cache_size = getattr(encoder, "model_cache_size_bytes", None)
    if cache_size is not None:
        dense_model["model_cache_size_bytes"] = cache_size

    held_out = slices["candidate_test"]["results"]
    expanded_results = slices["expanded_synthetic"]["results"]
    promotion_checks = {
        "candidate_labels_human_reviewed": label_summary[
            "human_review_gate_passed"
        ],
        "held_out_absence_accuracy_at_least_0_8": (
            held_out["dense"]["quality"]["evidence_absence_accuracy"] >= 0.8
        ),
        "expanded_recall_not_worse_than_sparse": (
            expanded_results["dense"]["quality"]["source_recall_at_k"]
            >= expanded_results["sparse_hybrid"]["quality"]["source_recall_at_k"]
        ),
        "held_out_dense_p95_below_50_ms": (
            held_out["dense"]["latency_ms"]["p95"] < 50.0
        ),
    }
    return {
        "schema_version": 1,
        "suite": "dense_retrieval_candidate_comparison_v1",
        "case_count": len(expanded),
        "existing_synthetic_case_count": len(existing_records),
        "candidate_case_count": len(candidate_records),
        "development_case_count": len(development),
        "held_out_test_case_count": len(test),
        "top_k": top_k,
        "runs_per_case": runs_per_case,
        "labels": label_summary,
        "dense_model": dense_model,
        "threshold_calibration": {
            "split": "candidate_development",
            "selection_objective": (
                "mean(source_recall_at_k, mean_reciprocal_rank, "
                "evidence_absence_accuracy)"
            ),
            "selected_threshold": selected_threshold,
            "tie_break": "lower_threshold_to_retain_evidence",
            "candidates": calibration,
        },
        "latency_methodology": {
            "corpus_embeddings": "precomputed_before_measured_search",
            "query_embeddings": "fresh_inference_on_every_measured_search",
            "model_loading": "excluded",
        },
        "production_decision": {
            "promotion_gate_passed": all(promotion_checks.values()),
            "checks": promotion_checks,
            "recommendation": (
                "retain_sparse_hybrid_and_evaluate_dense_candidate_fusion"
            ),
        },
        "slices": slices,
    }


def _require_human_reviewed(records: list[dict[str, object]]) -> None:
    pending = [
        record["case_id"]
        for record in records
        if record.get("label_provenance") != "human_reviewed"
        or record.get("label_status") != "reviewed"
    ]
    if pending:
        raise ValueError(
            "Human-review gate failed for candidate cases: " + ", ".join(pending)
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare sparse hybrid retrieval with optional dense embeddings."
    )
    parser.add_argument("--existing-dataset", action="append", type=Path)
    parser.add_argument(
        "--candidate-dataset", type=Path, default=DEFAULT_CANDIDATE_DATASET
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--model", default=DEFAULT_DENSE_MODEL)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--threads", type=int)
    parser.add_argument("--threshold", action="append", type=float)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--runs-per-case", type=int, default=10)
    parser.add_argument("--require-human-reviewed", action="store_true")
    args = parser.parse_args()

    existing_paths = (
        tuple(args.existing_dataset) if args.existing_dataset else DEFAULT_DATASETS
    )
    existing_records = [
        record
        for dataset_path in existing_paths
        for record in load_and_validate_dataset(dataset_path)
    ]
    candidate_records = load_and_validate_dataset(args.candidate_dataset)
    if args.require_human_reviewed:
        _require_human_reviewed(candidate_records)

    encoder = FastEmbedTextEncoder(
        model_name=args.model,
        cache_dir=args.cache_dir,
        threads=args.threads,
    )
    results = compare_dense_retrieval(
        existing_records,
        candidate_records,
        encoder=encoder,
        thresholds=(
            tuple(args.threshold) if args.threshold else DEFAULT_THRESHOLDS
        ),
        top_k=args.top_k,
        runs_per_case=args.runs_per_case,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        f"{json.dumps(results, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    held_out = results["slices"]["candidate_test"]
    sparse_quality = held_out["results"]["sparse_hybrid"]["quality"]
    dense_quality = held_out["results"]["dense"]["quality"]
    print(
        f"Compared {results['case_count']} cases with threshold "
        f"{results['threshold_calibration']['selected_threshold']:.2f}; "
        f"held-out sparse Recall@{args.top_k}="
        f"{sparse_quality['source_recall_at_k']:.4f}, "
        f"dense Recall@{args.top_k}={dense_quality['source_recall_at_k']:.4f}."
    )


if __name__ == "__main__":
    main()
