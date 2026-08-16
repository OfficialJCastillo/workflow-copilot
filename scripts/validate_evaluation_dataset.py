import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "evaluation" / "datasets" / "workflow_evidence_v1.jsonl"
DIFFICULTIES = {"easy", "medium", "hard"}
EXPECTED_BEHAVIORS = {
    "ask_for_missing_evidence",
    "grounded_plan",
    "surface_conflict",
}
CHALLENGE_TYPES = {
    "absence_with_distractors",
    "conflict_with_distractors",
    "context_completion",
    "false_friend",
    "multiple_distractors",
    "paraphrase",
    "paraphrase_with_distractors",
    "redundant_support",
}
REQUIRED_FIELDS = {
    "case_id",
    "workflow_type",
    "request_text",
    "evidence_documents",
    "expected_evidence",
    "answer_type",
    "difficulty",
    "expected_behavior",
}


def load_and_validate_dataset(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    case_ids: set[str] = set()

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Line {line_number} is not valid JSON: {error.msg}.") from error
        if not isinstance(record, dict):
            raise ValueError(f"Line {line_number} must contain a JSON object.")

        missing_fields = REQUIRED_FIELDS - set(record)
        if missing_fields:
            raise ValueError(
                f"Line {line_number} is missing fields: {', '.join(sorted(missing_fields))}."
            )

        case_id = record["case_id"]
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"Line {line_number} has an invalid case_id.")
        if case_id in case_ids:
            raise ValueError(f"Line {line_number} repeats case_id '{case_id}'.")
        case_ids.add(case_id)

        documents = record["evidence_documents"]
        expected_evidence = record["expected_evidence"]
        if not isinstance(documents, list) or not documents:
            raise ValueError(f"Line {line_number} must contain evidence documents.")
        if not isinstance(expected_evidence, list):
            raise ValueError(f"Line {line_number} has invalid expected_evidence.")

        source_ids = set()
        for document in documents:
            if not isinstance(document, dict):
                raise ValueError(f"Line {line_number} has an invalid evidence document.")
            if not {"source_id", "filename", "content"} <= set(document):
                raise ValueError(f"Line {line_number} has an incomplete evidence document.")
            source_id = document["source_id"]
            if not isinstance(source_id, str) or not source_id:
                raise ValueError(f"Line {line_number} has an invalid source_id.")
            source_ids.add(source_id)

        missing_sources = set(expected_evidence) - source_ids
        if missing_sources:
            raise ValueError(
                f"Line {line_number} references unknown evidence: {', '.join(sorted(missing_sources))}."
            )
        if record["difficulty"] not in DIFFICULTIES:
            raise ValueError(f"Line {line_number} has an unsupported difficulty.")
        if record["expected_behavior"] not in EXPECTED_BEHAVIORS:
            raise ValueError(f"Line {line_number} has an unsupported expected_behavior.")
        challenge_type = record.get("challenge_type")
        if challenge_type is not None and challenge_type not in CHALLENGE_TYPES:
            raise ValueError(f"Line {line_number} has an unsupported challenge_type.")

        records.append(record)

    if not records:
        raise ValueError("The evaluation dataset is empty.")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the workflow evidence benchmark.")
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args()
    records = load_and_validate_dataset(args.path)
    print(f"Validated {len(records)} evaluation cases from {args.path}.")


if __name__ == "__main__":
    main()
