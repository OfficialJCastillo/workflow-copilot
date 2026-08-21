from collections.abc import Sequence

from scripts.compare_fusion_retrieval import compare_fusion_retrieval


class ComparisonStubEncoder:
    model_name = "comparison-stub"
    dimension = 2

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        vectors = []
        for text in texts:
            if "relevant" in text.casefold() or "answer" in text.casefold():
                vectors.append((1.0, 0.0))
            else:
                vectors.append((0.0, 1.0))
        return vectors


def _record(
    case_id: str,
    *,
    split: str,
    request: str,
    expected: list[str],
    content: str,
) -> dict[str, object]:
    source_id = "answer" if expected else "distractor"
    return {
        "case_id": case_id,
        "request_text": request,
        "expected_evidence": expected,
        "evidence_documents": [
            {
                "source_id": source_id,
                "filename": f"{source_id}.txt",
                "content": content,
            }
        ],
        "split": split,
        "label_provenance": "synthetic_candidate",
        "label_status": "pending_human_review",
    }


def test_comparison_records_quality_but_blocks_promotion() -> None:
    candidates = [
        _record(
            "dev-positive",
            split="development",
            request="What is the relevant requirement?",
            expected=["answer"],
            content="Relevant answer.",
        ),
        _record(
            "dev-absence",
            split="development",
            request="Which executive approved the exception?",
            expected=[],
            content="An exception may be granted.",
        ),
        _record(
            "evaluation-positive",
            split="test",
            request="What is the relevant requirement?",
            expected=["answer"],
            content="Relevant answer.",
        ),
        _record(
            "evaluation-absence",
            split="test",
            request="What was the final outcome of the test?",
            expected=[],
            content="The test is scheduled next week.",
        ),
    ]

    result = compare_fusion_retrieval(
        [],
        candidates,
        encoder=ComparisonStubEncoder(),
        thresholds=(0.0,),
        top_k=1,
        runs_per_case=1,
    )

    evaluation = result["slices"]["candidate_evaluation"]["results"]["fusion"]
    assert evaluation["quality"]["source_recall_at_k"] == 1.0
    assert evaluation["quality"]["evidence_absence_accuracy"] == 1.0
    assert result["evaluation_integrity"]["reported_as_held_out"] is False
    assert result["production_decision"]["promotion_gate_passed"] is False
