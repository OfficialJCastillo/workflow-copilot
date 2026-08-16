import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.hybrid_retrieval import HybridEvidenceRetriever
from app.services.retrieval import EvidenceRetriever
from scripts.evaluate_retrieval import evaluate_records
from scripts.validate_evaluation_dataset import DEFAULT_DATASET
from scripts.validate_evaluation_dataset import load_and_validate_dataset


DEFAULT_CHALLENGE_DATASET = (
    PROJECT_ROOT / "evaluation" / "datasets" / "workflow_evidence_challenge_v1.jsonl"
)
DEFAULT_RESULTS = (
    PROJECT_ROOT / "evaluation" / "results" / "retrieval_strategy_comparison_v1.json"
)


def _evaluate_slice(
    records: list[dict[str, object]],
    *,
    dataset_name: str,
    top_k: int,
    runs_per_case: int,
) -> dict[str, object]:
    return {
        "lexical": evaluate_records(
            records,
            top_k=top_k,
            runs_per_case=runs_per_case,
            retriever=EvidenceRetriever(),
            dataset_name=dataset_name,
        ),
        "hybrid": evaluate_records(
            records,
            top_k=top_k,
            runs_per_case=runs_per_case,
            retriever=HybridEvidenceRetriever(),
            dataset_name=dataset_name,
        ),
    }


def compare_strategies(
    core_records: list[dict[str, object]],
    challenge_records: list[dict[str, object]],
    *,
    top_k: int = 3,
    runs_per_case: int = 50,
) -> dict[str, object]:
    slices = {
        "core": _evaluate_slice(
            core_records,
            dataset_name="workflow_evidence_v1",
            top_k=top_k,
            runs_per_case=runs_per_case,
        ),
        "challenge": _evaluate_slice(
            challenge_records,
            dataset_name="workflow_evidence_challenge_v1",
            top_k=top_k,
            runs_per_case=runs_per_case,
        ),
        "combined": _evaluate_slice(
            [*core_records, *challenge_records],
            dataset_name="workflow_evidence_combined_v1",
            top_k=top_k,
            runs_per_case=runs_per_case,
        ),
    }
    combined_lexical = slices["combined"]["lexical"]["quality"]
    combined_hybrid = slices["combined"]["hybrid"]["quality"]
    return {
        "schema_version": 1,
        "suite": "workflow_evidence_combined_v1",
        "case_count": len(core_records) + len(challenge_records),
        "core_case_count": len(core_records),
        "challenge_case_count": len(challenge_records),
        "top_k": top_k,
        "runs_per_case": runs_per_case,
        "combined_quality_delta_hybrid_minus_lexical": {
            "source_recall_at_k": round(
                combined_hybrid["source_recall_at_k"]
                - combined_lexical["source_recall_at_k"],
                4,
            ),
            "mean_reciprocal_rank": round(
                combined_hybrid["mean_reciprocal_rank"]
                - combined_lexical["mean_reciprocal_rank"],
                4,
            ),
            "evidence_absence_accuracy": round(
                combined_hybrid["evidence_absence_accuracy"]
                - combined_lexical["evidence_absence_accuracy"],
                4,
            ),
        },
        "slices": slices,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare lexical and hybrid retrieval.")
    parser.add_argument("--core-dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--challenge-dataset",
        type=Path,
        default=DEFAULT_CHALLENGE_DATASET,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--runs-per-case", type=int, default=50)
    args = parser.parse_args()
    results = compare_strategies(
        load_and_validate_dataset(args.core_dataset),
        load_and_validate_dataset(args.challenge_dataset),
        top_k=args.top_k,
        runs_per_case=args.runs_per_case,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(f"{json.dumps(results, indent=2, sort_keys=True)}\n", encoding="utf-8")
    combined = results["slices"]["combined"]
    print(
        f"Compared {results['case_count']} cases: "
        f"lexical Recall@{results['top_k']}="
        f"{combined['lexical']['quality']['source_recall_at_k']:.4f}, "
        f"hybrid Recall@{results['top_k']}="
        f"{combined['hybrid']['quality']['source_recall_at_k']:.4f}."
    )


if __name__ == "__main__":
    main()
