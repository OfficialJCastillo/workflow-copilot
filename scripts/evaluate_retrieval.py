import argparse
import json
import platform
from pathlib import Path
import sys
from time import perf_counter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.retrieval import EvidenceRetriever
from app.services.retrieval import SearchDocument
from scripts.validate_evaluation_dataset import DEFAULT_DATASET
from scripts.validate_evaluation_dataset import load_and_validate_dataset


DEFAULT_RESULTS = PROJECT_ROOT / "evaluation" / "results" / "retrieval_baseline_v1.json"


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = rank - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def evaluate_records(
    records: list[dict[str, object]],
    *,
    top_k: int = 3,
    runs_per_case: int = 50,
    retriever: EvidenceRetriever | None = None,
    dataset_name: str = "workflow_evidence_v1",
) -> dict[str, object]:
    retriever = retriever or EvidenceRetriever()
    case_results: list[dict[str, object]] = []
    recall_values: list[float] = []
    reciprocal_ranks: list[float] = []
    absence_checks: list[float] = []
    latencies_ms: list[float] = []

    for record in records:
        documents = [
            SearchDocument(
                source_id=document["source_id"],
                citation_id=document["source_id"],
                filename=document["filename"],
                content=document["content"],
            )
            for document in record["evidence_documents"]
        ]
        retrieval = None
        for _ in range(runs_per_case):
            started = perf_counter()
            retrieval = retriever.search(
                query=record["request_text"],
                documents=documents,
                top_k=top_k,
            )
            latencies_ms.append((perf_counter() - started) * 1_000)
        assert retrieval is not None

        retrieved_sources = list(
            dict.fromkeys(result.source_id for result in retrieval.results)
        )
        expected_sources = set(record["expected_evidence"])
        if expected_sources:
            recalled = len(expected_sources & set(retrieved_sources)) / len(expected_sources)
            recall_values.append(recalled)
            first_relevant_rank = next(
                (
                    index
                    for index, source_id in enumerate(retrieved_sources, start=1)
                    if source_id in expected_sources
                ),
                None,
            )
            reciprocal_rank = 1 / first_relevant_rank if first_relevant_rank else 0.0
            reciprocal_ranks.append(reciprocal_rank)
            absence_correct = None
        else:
            recalled = None
            reciprocal_rank = None
            absence_correct = not retrieved_sources
            absence_checks.append(float(absence_correct))

        case_results.append(
            {
                "case_id": record["case_id"],
                "expected_sources": sorted(expected_sources),
                "retrieved_sources": retrieved_sources,
                "recall_at_k": recalled,
                "reciprocal_rank": reciprocal_rank,
                "evidence_absence_correct": absence_correct,
            }
        )

    return {
        "schema_version": 1,
        "dataset": dataset_name,
        "retriever": retriever.strategy_name,
        "top_k": top_k,
        "case_count": len(records),
        "cases_with_expected_evidence": len(recall_values),
        "quality": {
            "source_recall_at_k": round(sum(recall_values) / len(recall_values), 4),
            "mean_reciprocal_rank": round(
                sum(reciprocal_ranks) / len(reciprocal_ranks), 4
            ),
            "evidence_absence_accuracy": round(
                sum(absence_checks) / len(absence_checks), 4
            ) if absence_checks else None,
        },
        "latency_ms": {
            "sample_count": len(latencies_ms),
            "p50": round(_percentile(latencies_ms, 0.50), 4),
            "p95": round(_percentile(latencies_ms, 0.95), 4),
            "maximum": round(max(latencies_ms), 4),
        },
        "methodology": {
            "chunk_words": retriever.chunk_words,
            "overlap_words": retriever.overlap_words,
            "runs_per_case": runs_per_case,
            "corpus": "synthetic",
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "cases": case_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the lexical evidence retriever.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--runs-per-case", type=int, default=50)
    args = parser.parse_args()
    records = load_and_validate_dataset(args.dataset)
    results = evaluate_records(
        records,
        top_k=args.top_k,
        runs_per_case=args.runs_per_case,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(f"{json.dumps(results, indent=2, sort_keys=True)}\n", encoding="utf-8")
    quality = results["quality"]
    print(
        "Evaluated "
        f"{results['case_count']} cases: "
        f"Recall@{results['top_k']}={quality['source_recall_at_k']:.4f}, "
        f"MRR={quality['mean_reciprocal_rank']:.4f}, "
        f"P95={results['latency_ms']['p95']:.4f} ms."
    )


if __name__ == "__main__":
    main()
