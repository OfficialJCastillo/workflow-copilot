from collections.abc import Sequence

import pytest

from scripts.compare_dense_retrieval import _calibrate_threshold
from scripts.compare_dense_retrieval import _require_human_reviewed
from scripts.compare_dense_retrieval import compare_dense_retrieval


class CalibrationStubEncoder:
    model_name = "calibration-stub"
    dimension = 2

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        vectors = []
        for text in texts:
            normalized = text.casefold()
            if "relevant" in normalized or "answer" in normalized:
                vectors.append((1.0, 0.0))
            else:
                vectors.append((0.0, 1.0))
        return vectors


def _record(
    case_id: str,
    *,
    query: str,
    expected: list[str],
    split: str | None = None,
) -> dict[str, object]:
    record = {
        "case_id": case_id,
        "request_text": query,
        "expected_evidence": expected,
        "evidence_documents": [
            {
                "source_id": "answer" if expected else "distractor",
                "filename": "evidence.txt",
                "content": "Relevant answer." if expected else "Unrelated schedule.",
            }
        ],
    }
    if split is not None:
        record.update(
            {
                "split": split,
                "label_provenance": "synthetic_candidate",
                "label_status": "pending_human_review",
            }
        )
    return record


def test_calibration_selects_lowest_equally_accurate_threshold() -> None:
    threshold, rows = _calibrate_threshold(
        [
            _record("positive", query="relevant requirement", expected=["answer"]),
            _record("absence", query="relevant missing", expected=[]),
        ],
        encoder=CalibrationStubEncoder(),
        thresholds=(0.4, 0.6),
        top_k=1,
    )

    assert threshold == 0.4
    assert len(rows) == 2


def test_human_review_gate_rejects_candidate_labels() -> None:
    with pytest.raises(ValueError, match="candidate-001"):
        _require_human_reviewed(
            [
                {
                    "case_id": "candidate-001",
                    "label_provenance": "synthetic_candidate",
                    "label_status": "pending_human_review",
                }
            ]
        )


def test_comparison_records_failed_promotion_gate() -> None:
    candidates = [
        _record(
            "dev-positive",
            query="relevant requirement",
            expected=["answer"],
            split="development",
        ),
        _record(
            "dev-absence",
            query="relevant missing",
            expected=[],
            split="development",
        ),
        _record(
            "test-positive",
            query="relevant requirement",
            expected=["answer"],
            split="test",
        ),
        _record(
            "test-absence",
            query="relevant missing",
            expected=[],
            split="test",
        ),
    ]

    result = compare_dense_retrieval(
        [],
        candidates,
        encoder=CalibrationStubEncoder(),
        thresholds=(0.4,),
        top_k=1,
        runs_per_case=1,
    )

    assert result["labels"]["pending_human_review_case_count"] == 4
    assert result["dense_model"]["production_dependency"] is False
    assert result["production_decision"]["promotion_gate_passed"] is False
