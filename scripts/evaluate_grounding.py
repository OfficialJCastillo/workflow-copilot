import argparse
import json
import platform
from pathlib import Path
import re
import sys
from time import perf_counter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.grounding import ANSWERER_NAME
from app.services.grounding import GroundedAnswerService
from app.services.hybrid_retrieval import HybridEvidenceRetriever
from app.services.retrieval import EvidenceRetriever
from app.services.retrieval import SearchDocument
from scripts.evaluate_retrieval import _percentile
from scripts.validate_evaluation_dataset import DEFAULT_DATASET
from scripts.validate_evaluation_dataset import load_and_validate_dataset


DEFAULT_RESULTS = PROJECT_ROOT / "evaluation" / "results" / "grounded_answer_baseline_v1.json"


def _expected_status(record: dict[str, object]) -> str:
    if record["expected_behavior"] in {"grounded_plan", "surface_conflict"}:
        return "grounded"
    if record["expected_evidence"]:
        return "partial_evidence"
    return "insufficient_evidence"


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def evaluate_grounded_answers(
    records: list[dict[str, object]],
    *,
    top_k: int = 3,
    max_claims: int = 5,
    runs_per_case: int = 50,
    retriever: EvidenceRetriever | None = None,
    dataset_name: str = "workflow_evidence_v1",
) -> dict[str, object]:
    retriever = retriever or EvidenceRetriever()
    service = GroundedAnswerService(retriever)
    case_results: list[dict[str, object]] = []
    behavior_checks: list[float] = []
    citation_checks: list[float] = []
    citation_coverage_checks: list[float] = []
    expected_source_checks: list[float] = []
    expected_source_recall_values: list[float] = []
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
        source_text = {
            document.source_id: _normalized(document.content)
            for document in documents
        }
        answer = None
        for _ in range(runs_per_case):
            started = perf_counter()
            answer = service.answer(
                query=record["request_text"],
                documents=documents,
                top_k=top_k,
                max_claims=max_claims,
            )
            latencies_ms.append((perf_counter() - started) * 1_000)
        assert answer is not None

        expected_status = _expected_status(record)
        behavior_correct = answer.status == expected_status
        behavior_checks.append(float(behavior_correct))
        expected_sources = set(record["expected_evidence"])
        cited_sources: list[str] = []
        supported_claims: list[bool] = []
        for claim in answer.claims:
            cited_sources.append(claim.source_id)
            supported = _normalized(claim.text) in source_text.get(claim.source_id, "")
            supported_claims.append(supported)
            citation_checks.append(float(supported))
            citation_coverage_checks.append(float(bool(claim.citation_id)))
            expected_source_checks.append(float(claim.source_id in expected_sources))

        cited_source_set = set(cited_sources)
        expected_source_recall = (
            len(cited_source_set & expected_sources) / len(expected_sources)
            if expected_sources
            else None
        )
        if expected_source_recall is not None:
            expected_source_recall_values.append(expected_source_recall)

        case_results.append(
            {
                "case_id": record["case_id"],
                "expected_status": expected_status,
                "actual_status": answer.status,
                "behavior_correct": behavior_correct,
                "query_term_coverage": answer.query_term_coverage,
                "claim_count": len(answer.claims),
                "cited_sources": list(dict.fromkeys(cited_sources)),
                "supported_claims": sum(supported_claims),
                "expected_source_recall": expected_source_recall,
                "context_policy": answer.context_policy,
                "excluded_result_count": answer.excluded_result_count,
            }
        )

    citation_correctness = sum(citation_checks) / len(citation_checks) if citation_checks else 1.0
    return {
        "schema_version": 1,
        "dataset": dataset_name,
        "answerer": ANSWERER_NAME,
        "retriever": retriever.strategy_name,
        "case_count": len(records),
        "claim_count": len(citation_checks),
        "quality": {
            "grounding_behavior_accuracy": round(sum(behavior_checks) / len(behavior_checks), 4),
            "citation_correctness": round(citation_correctness, 4),
            "citation_coverage": round(
                sum(citation_coverage_checks) / len(citation_coverage_checks), 4
            ) if citation_coverage_checks else 1.0,
            "expected_source_precision": round(
                sum(expected_source_checks) / len(expected_source_checks), 4
            ) if expected_source_checks else 1.0,
            "expected_source_recall": round(
                sum(expected_source_recall_values) / len(expected_source_recall_values), 4
            ) if expected_source_recall_values else 1.0,
            "unsupported_claim_rate": round(1 - citation_correctness, 4),
        },
        "latency_ms": {
            "sample_count": len(latencies_ms),
            "p50": round(_percentile(latencies_ms, 0.50), 4),
            "p95": round(_percentile(latencies_ms, 0.95), 4),
            "maximum": round(max(latencies_ms), 4),
        },
        "methodology": {
            "top_k": top_k,
            "max_claims": max_claims,
            "runs_per_case": runs_per_case,
            "corpus": "synthetic",
            "support_check": "normalized claim text is contained by its cited source",
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "cases": case_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate deterministic grounded answers.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--max-claims", type=int, default=5)
    parser.add_argument("--runs-per-case", type=int, default=50)
    parser.add_argument(
        "--additional-dataset",
        action="append",
        type=Path,
        default=[],
    )
    parser.add_argument(
        "--strategy",
        choices=("lexical", "hybrid"),
        default="lexical",
    )
    args = parser.parse_args()
    retriever = (
        HybridEvidenceRetriever()
        if args.strategy == "hybrid"
        else EvidenceRetriever()
    )
    records = load_and_validate_dataset(args.dataset)
    for additional_dataset in args.additional_dataset:
        records.extend(load_and_validate_dataset(additional_dataset))
    dataset_name = (
        "workflow_evidence_combined_v1"
        if args.additional_dataset
        else args.dataset.stem
    )
    results = evaluate_grounded_answers(
        records,
        top_k=args.top_k,
        max_claims=args.max_claims,
        runs_per_case=args.runs_per_case,
        retriever=retriever,
        dataset_name=dataset_name,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(f"{json.dumps(results, indent=2, sort_keys=True)}\n", encoding="utf-8")
    quality = results["quality"]
    print(
        "Evaluated "
        f"{results['case_count']} cases and {results['claim_count']} claims: "
        f"behavior={quality['grounding_behavior_accuracy']:.4f}, "
        f"citation correctness={quality['citation_correctness']:.4f}, "
        f"unsupported claim rate={quality['unsupported_claim_rate']:.4f}, "
        f"P95={results['latency_ms']['p95']:.4f} ms."
    )


if __name__ == "__main__":
    main()
