import argparse
import json
from pathlib import Path
import sys
from time import perf_counter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.dense_retrieval import DEFAULT_DENSE_MODEL
from app.services.dense_retrieval import DenseTextEncoder
from app.services.dense_retrieval import FastEmbedTextEncoder
from app.services.fusion_retrieval import FusionEvidenceRetriever
from app.services.hybrid_retrieval import HybridEvidenceRetriever
from scripts.compare_dense_retrieval import DEFAULT_CANDIDATE_DATASET
from scripts.compare_dense_retrieval import _documents
from scripts.compare_dense_retrieval import _label_summary
from scripts.compare_dense_retrieval import _quality_delta
from scripts.compare_persisted_hybrid import DEFAULT_DATASETS
from scripts.evaluate_retrieval import evaluate_records
from scripts.validate_evaluation_dataset import load_and_validate_dataset


DEFAULT_RESULTS = (
    PROJECT_ROOT
    / "evaluation"
    / "results"
    / "fusion_retrieval_candidate_comparison_v1.json"
)
DEFAULT_THRESHOLDS = tuple(round(value / 100, 2) for value in range(0, 51, 5))
SPARSE_WEIGHT = 0.15


def _objective(quality: dict[str, float | None]) -> float:
    metrics = (
        quality["source_recall_at_k"],
        quality["mean_reciprocal_rank"],
        quality["evidence_absence_accuracy"],
    )
    values = [float(metric) for metric in metrics if metric is not None]
    return sum(values) / len(values)


def _calibrate_fusion_threshold(
    records: list[dict[str, object]],
    *,
    encoder: DenseTextEncoder,
    thresholds: tuple[float, ...],
    top_k: int,
) -> tuple[float, list[dict[str, object]]]:
    if not records:
        raise ValueError("Fusion calibration requires development cases.")
    if not thresholds:
        raise ValueError("At least one fusion threshold is required.")

    candidates: list[dict[str, object]] = []
    for threshold in sorted(set(thresholds)):
        result = evaluate_records(
            records,
            top_k=top_k,
            runs_per_case=1,
            retriever=FusionEvidenceRetriever(
                encoder,
                minimum_dense_similarity=threshold,
                sparse_weight=SPARSE_WEIGHT,
                cache_queries=True,
            ),
            dataset_name="fusion_candidate_development_v1",
        )
        candidates.append(
            {
                "threshold": threshold,
                "objective": round(_objective(result["quality"]), 4),
                "quality": result["quality"],
            }
        )
    selected = max(
        candidates,
        key=lambda row: (
            row["objective"],
            row["quality"]["source_recall_at_k"],
            row["quality"]["mean_reciprocal_rank"],
            -row["threshold"],
        ),
    )
    return float(selected["threshold"]), candidates


def _evaluate_slice(
    records: list[dict[str, object]],
    *,
    dataset_name: str,
    encoder: DenseTextEncoder,
    threshold: float,
    top_k: int,
    runs_per_case: int,
) -> dict[str, object]:
    fusion = FusionEvidenceRetriever(
        encoder,
        minimum_dense_similarity=threshold,
        sparse_weight=SPARSE_WEIGHT,
        cache_queries=False,
    )
    prewarm_started = perf_counter()
    chunk_count = 0
    for record in records:
        chunk_count += fusion.prepare_documents(_documents(record)).chunk_count
    prewarm_ms = (perf_counter() - prewarm_started) * 1_000

    sparse = evaluate_records(
        records,
        top_k=top_k,
        runs_per_case=runs_per_case,
        retriever=HybridEvidenceRetriever(),
        dataset_name=dataset_name,
    )
    fused = evaluate_records(
        records,
        top_k=top_k,
        runs_per_case=runs_per_case,
        retriever=fusion,
        dataset_name=dataset_name,
    )
    return {
        "quality_delta_fusion_minus_sparse": _quality_delta(
            fused["quality"], sparse["quality"]
        ),
        "fusion_corpus_prewarm": {
            "latency_ms": round(prewarm_ms, 4),
            "corpus_count": fusion.dense.corpus_cache_misses,
            "chunk_count": chunk_count,
        },
        "results": {
            "sparse_hybrid": sparse,
            "fusion": fused,
        },
    }


def compare_fusion_retrieval(
    existing_records: list[dict[str, object]],
    candidate_records: list[dict[str, object]],
    *,
    encoder: DenseTextEncoder,
    thresholds: tuple[float, ...] = DEFAULT_THRESHOLDS,
    top_k: int = 3,
    runs_per_case: int = 10,
) -> dict[str, object]:
    if top_k < 1 or runs_per_case < 1:
        raise ValueError("top_k and runs_per_case must be at least 1.")
    development = [
        record for record in candidate_records if record.get("split") == "development"
    ]
    evaluation = [
        record for record in candidate_records if record.get("split") == "test"
    ]
    if not development or not evaluation:
        raise ValueError("Candidate labels require development and evaluation splits.")

    threshold, calibration = _calibrate_fusion_threshold(
        development,
        encoder=encoder,
        thresholds=thresholds,
        top_k=top_k,
    )
    expanded = [*existing_records, *candidate_records]
    slices = {
        name: _evaluate_slice(
            records,
            dataset_name=name,
            encoder=encoder,
            threshold=threshold,
            top_k=top_k,
            runs_per_case=runs_per_case,
        )
        for name, records in {
            "candidate_development": development,
            "candidate_evaluation": evaluation,
            "candidate_combined": candidate_records,
            "expanded_synthetic": expanded,
        }.items()
    }
    labels = _label_summary(expanded, candidate_records)
    evaluation_results = slices["candidate_evaluation"]["results"]
    expanded_results = slices["expanded_synthetic"]["results"]
    checks = {
        "candidate_labels_human_reviewed": labels["human_review_gate_passed"],
        "evaluation_split_blind": False,
        "evaluation_absence_accuracy_at_least_0_8": (
            evaluation_results["fusion"]["quality"][
                "evidence_absence_accuracy"
            ] >= 0.8
        ),
        "expanded_recall_not_worse_than_sparse": (
            expanded_results["fusion"]["quality"]["source_recall_at_k"]
            >= expanded_results["sparse_hybrid"]["quality"]["source_recall_at_k"]
        ),
        "expanded_absence_not_worse_than_sparse": (
            expanded_results["fusion"]["quality"]["evidence_absence_accuracy"]
            >= expanded_results["sparse_hybrid"]["quality"][
                "evidence_absence_accuracy"
            ]
        ),
        "evaluation_fusion_p95_below_50_ms": (
            evaluation_results["fusion"]["latency_ms"]["p95"] < 50.0
        ),
    }
    model = {
        "name": encoder.model_name,
        "embedding_dimension": encoder.dimension,
        "runtime_dependency": "fastembed==0.8.0",
        "production_dependency": False,
    }
    cache_size = getattr(encoder, "model_cache_size_bytes", None)
    if cache_size is not None:
        model["model_cache_size_bytes"] = cache_size

    return {
        "schema_version": 1,
        "suite": "fusion_retrieval_candidate_comparison_v1",
        "case_count": len(expanded),
        "candidate_case_count": len(candidate_records),
        "development_case_count": len(development),
        "evaluation_case_count": len(evaluation),
        "top_k": top_k,
        "runs_per_case": runs_per_case,
        "labels": labels,
        "evaluation_integrity": {
            "split_name_in_source_dataset": "test",
            "reported_as_held_out": False,
            "blinding_status": "inspected_during_gate_design",
        },
        "model": model,
        "fusion_policy": {
            "dense_weight": 1.0 - SPARSE_WEIGHT,
            "sparse_weight": SPARSE_WEIGHT,
            "sparse_score_normalization": "divide_by_query_max",
            "preserve_sparse_compound_abstention": True,
            "answer_slot_gates": ["authorization_actor", "outcome_status"],
            "selected_dense_threshold": threshold,
        },
        "threshold_calibration": {
            "split": "candidate_development",
            "selected_threshold": threshold,
            "candidates": calibration,
        },
        "latency_methodology": {
            "corpus_embeddings": "precomputed_before_measured_search",
            "query_embeddings": "fresh_inference_on_every_measured_search",
            "model_loading": "excluded",
        },
        "production_decision": {
            "promotion_gate_passed": all(checks.values()),
            "checks": checks,
            "recommendation": "keep_evaluation_only_pending_human_review_and_blind_test",
        },
        "slices": slices,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare sparse hybrid retrieval with gated sparse+dense fusion."
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
    encoder = FastEmbedTextEncoder(
        model_name=args.model,
        cache_dir=args.cache_dir,
        threads=args.threads,
    )
    result = compare_fusion_retrieval(
        existing_records,
        candidate_records,
        encoder=encoder,
        thresholds=tuple(args.threshold) if args.threshold else DEFAULT_THRESHOLDS,
        top_k=args.top_k,
        runs_per_case=args.runs_per_case,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        f"{json.dumps(result, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    evaluation = result["slices"]["candidate_evaluation"]["results"]
    print(
        f"Compared {result['case_count']} cases; candidate-evaluation "
        f"sparse/fusion Recall@{args.top_k}="
        f"{evaluation['sparse_hybrid']['quality']['source_recall_at_k']:.4f}/"
        f"{evaluation['fusion']['quality']['source_recall_at_k']:.4f}, "
        f"promotion={result['production_decision']['promotion_gate_passed']}."
    )


if __name__ == "__main__":
    main()
