from pathlib import Path

from scripts.validate_evaluation_dataset import DEFAULT_DATASET
from scripts.validate_evaluation_dataset import load_and_validate_dataset


CONTEXT_POLICY_DATASET = (
    Path(__file__).resolve().parents[1]
    / "evaluation"
    / "datasets"
    / "workflow_evidence_context_policy_v1.jsonl"
)


def test_versioned_evaluation_dataset_is_valid_and_varied() -> None:
    records = load_and_validate_dataset(DEFAULT_DATASET)

    assert len(records) >= 6
    assert {record["difficulty"] for record in records} == {"easy", "medium", "hard"}
    assert {
        "ask_for_missing_evidence",
        "grounded_plan",
        "surface_conflict",
    } <= {record["expected_behavior"] for record in records}
    assert len({record["workflow_type"] for record in records}) >= 4


def test_context_policy_dataset_is_valid_and_adversarial() -> None:
    records = load_and_validate_dataset(CONTEXT_POLICY_DATASET)

    assert len(records) == 6
    assert {record["challenge_type"] for record in records} == {
        "absence_with_distractors",
        "context_completion",
        "false_friend",
        "redundant_support",
    }
    assert sum(not record["expected_evidence"] for record in records) == 1
