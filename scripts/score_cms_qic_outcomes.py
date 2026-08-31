#!/usr/bin/env python3
"""Score Appeal's predictions against the explicit CMS QIC outcome field.

This is the official-outcome track only. It does not infer a legal ground,
does not use human legal-ground annotations, and cannot claim a complete
Appeal evaluation. The benchmark keeps the CMS ``Decision`` value in
``hidden_labels`` while the model input is outcome-blinded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from appeal_evaluation import wilson_interval
from inspect_cms_qic_bulk import sha256_file
from sample_cms_qic_benchmark import require_external


ROOT = Path(__file__).resolve().parents[1]
HASH_LENGTH = 64
ABSTAINED_LABEL = "<abstained>"
FORBIDDEN_PREDICTION_KEYS = frozenset(
    {
        "hidden_labels",
        "model_input",
        "decision_rationale",
        "policy_context",
        "raw_row",
        "source_row",
        "gold",
    }
)


def normalize_label(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return " ".join(value.split()).casefold()


def case_ref(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != HASH_LENGTH or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def json_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"{label} contains a blank line at {line_number}")
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{label} row {line_number} is not an object")
            result.append(value)
    return result


def benchmark_outcomes(
    benchmark_path: Path,
    manifest_path: Path,
) -> tuple[dict[str, str], dict[str, Any], str]:
    benchmark_path = require_external(benchmark_path, "CMS legal-ground benchmark")
    manifest = json_object(manifest_path, "CMS legal-ground benchmark manifest")
    if manifest.get("status") != "cms_qic_legal_ground_benchmark_sample_ready":
        raise ValueError("benchmark manifest is not the versioned legal-ground sample")
    artifact = manifest.get("artifact")
    sampling = manifest.get("sampling")
    if not isinstance(artifact, dict) or not isinstance(sampling, dict):
        raise ValueError("benchmark manifest lacks artifact or sampling metadata")
    expected_hash = artifact.get("sha256")
    if not isinstance(expected_hash, str) or sha256_file(benchmark_path) != expected_hash:
        raise ValueError("benchmark file hash does not match its manifest")

    outcomes: dict[str, str] = {}
    all_case_refs: list[str] = []
    for index, record in enumerate(read_jsonl(benchmark_path, "benchmark"), start=1):
        reference = case_ref(record.get("case_ref"), f"benchmark row {index}.case_ref")
        if reference in outcomes:
            raise ValueError(f"benchmark repeats case_ref at row {index}")
        split = record.get("split")
        if split not in {"development", "locked_test"}:
            raise ValueError(f"benchmark row {index} has an unsupported split")
        model_input = record.get("model_input")
        hidden_labels = record.get("hidden_labels")
        if not isinstance(model_input, dict) or not isinstance(hidden_labels, dict):
            raise ValueError(f"benchmark row {index} lacks model_input or hidden_labels")
        if "regulator_outcome" in model_input or "hidden_labels" in model_input:
            raise ValueError(f"benchmark row {index} exposes the outcome in model_input")
        outcome = normalize_label(hidden_labels.get("regulator_outcome"), f"benchmark row {index}.hidden_labels.regulator_outcome")
        all_case_refs.append(reference)
        if split == "locked_test":
            outcomes[reference] = outcome

    split_counts = sampling.get("split_counts")
    locked_size = sampling.get("locked_test_size")
    if not isinstance(split_counts, dict) or not isinstance(locked_size, int):
        raise ValueError("benchmark sampling metadata is incomplete")
    observed_splits = Counter(
        record.get("split") for record in read_jsonl(benchmark_path, "benchmark")
    )
    if dict(sorted(observed_splits.items())) != split_counts:
        raise ValueError("benchmark split counts do not match its manifest")
    if len(outcomes) != locked_size:
        raise ValueError("benchmark locked-test count does not match its manifest")
    expected_identity = sampling.get("sample_identity_sha256")
    digest = hashlib.sha256()
    for reference in sorted(all_case_refs):
        digest.update(reference.encode("ascii"))
        digest.update(b"\n")
    if digest.hexdigest() != expected_identity:
        raise ValueError("benchmark sample identity does not match its manifest")
    return outcomes, manifest, expected_hash


def prediction_outcomes(path: Path, expected: set[str]) -> dict[str, str | None]:
    path = require_external(path, "CMS outcome predictions")
    result: dict[str, str | None] = {}
    for index, row in enumerate(read_jsonl(path, "prediction"), start=1):
        unknown = set(row) - {"case_ref", "regulator_outcome", "abstained"}
        forbidden = unknown.intersection(FORBIDDEN_PREDICTION_KEYS)
        if forbidden:
            raise ValueError(f"prediction row {index} contains forbidden field(s): {', '.join(sorted(forbidden))}")
        if unknown:
            raise ValueError(f"prediction row {index} contains unsupported fields: {', '.join(sorted(unknown))}")
        reference = case_ref(row.get("case_ref"), f"prediction row {index}.case_ref")
        if reference in result:
            raise ValueError(f"prediction repeats case_ref at row {index}")
        abstained = row.get("abstained", False)
        if not isinstance(abstained, bool):
            raise ValueError(f"prediction row {index}.abstained must be boolean")
        value = row.get("regulator_outcome")
        if abstained:
            if value is not None:
                raise ValueError(f"prediction row {index} cannot provide an outcome while abstaining")
            result[reference] = None
        else:
            result[reference] = normalize_label(value, f"prediction row {index}.regulator_outcome")
    if set(result) != expected:
        missing = sorted(expected - set(result))
        extra = sorted(set(result) - expected)
        raise ValueError(f"prediction coverage mismatch: missing={missing}, extra={extra}")
    return result


def confidence(correct: int, total: int) -> list[float] | None:
    if total == 0:
        return None
    low, high = wilson_interval(correct, total)
    return [low, high]


def macro_f1(gold: dict[str, str], predictions: dict[str, str | None]) -> dict[str, Any]:
    observed = {value for value in predictions.values() if value is not None}
    labels = sorted(set(gold.values()) | observed)
    per_label: dict[str, dict[str, float | int]] = {}
    scores: list[float] = []
    for label in labels:
        true_positive = sum(predictions[reference] == label and expected == label for reference, expected in gold.items())
        false_positive = sum(predictions[reference] == label and expected != label for reference, expected in gold.items())
        false_negative = sum(predictions[reference] != label and expected == label for reference, expected in gold.items())
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": sum(expected == label for expected in gold.values()),
        }
        scores.append(f1)
    return {
        "value": sum(scores) / len(scores) if scores else None,
        "labels": per_label,
        "abstentions_excluded": True,
    }


def score(
    benchmark_path: Path,
    manifest_path: Path,
    predictions_path: Path,
    output_path: Path,
    *,
    code_revision: str | None = None,
) -> dict[str, Any]:
    gold, manifest, benchmark_hash = benchmark_outcomes(benchmark_path, manifest_path)
    predictions = prediction_outcomes(predictions_path, set(gold))
    non_abstained = {reference: value for reference, value in predictions.items() if value is not None}
    selective_correct = sum(non_abstained[reference] == gold[reference] for reference in non_abstained)
    overall_correct = sum(predictions[reference] == gold[reference] for reference in gold)
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for reference, expected in sorted(gold.items()):
        observed = predictions[reference] if predictions[reference] is not None else ABSTAINED_LABEL
        confusion[expected][observed] += 1
    locked_count = len(gold)
    coverage = len(non_abstained) / locked_count if locked_count else 0.0
    selective_value = selective_correct / len(non_abstained) if non_abstained else None
    return {
        "schema_version": "1.0",
        "status": "cms_qic_official_outcome_score_ready",
        "track": {
            "name": "regulator_outcome",
            "gold_source": "hidden_labels.regulator_outcome",
            "official_source_field": "Decision",
            "label_type": "explicit_CMS_QIC_regulator_outcome",
            "legal_ground_scoring": "separate_track",
            "full_appeal_evaluation": False,
        },
        "source": {
            "benchmark_sha256": benchmark_hash,
            "benchmark_manifest_sha256": sha256_file(manifest_path),
            "benchmark_status": manifest.get("status"),
            "locked_test_count": locked_count,
            "narratives_in_report": False,
        },
        "prediction_artifact": {
            "sha256": sha256_file(predictions_path.expanduser().resolve()),
            "location": "outside_repository_only",
            "code_revision": code_revision,
        },
        "metrics": {
            "accuracy_including_abstentions_as_incorrect": {
                "value": overall_correct / locked_count if locked_count else None,
                "numerator": overall_correct,
                "denominator": locked_count,
                "confidence_95": confidence(overall_correct, locked_count),
            },
            "selective_accuracy": {
                "value": selective_value,
                "numerator": selective_correct,
                "denominator": len(non_abstained),
                "confidence_95": confidence(selective_correct, len(non_abstained)),
            },
            "coverage": {
                "value": coverage,
                "numerator": len(non_abstained),
                "denominator": locked_count,
            },
            "abstention_rate": {
                "value": (locked_count - len(non_abstained)) / locked_count if locked_count else 0.0,
                "numerator": locked_count - len(non_abstained),
                "denominator": locked_count,
            },
            "macro_f1_on_non_abstained": macro_f1(gold, predictions),
        },
        "distributions": {
            "gold_outcomes": dict(sorted(Counter(gold.values()).items())),
            "predicted_outcomes": dict(sorted(Counter(value for value in predictions.values() if value is not None).items())),
            "abstentions": sum(value is None for value in predictions.values()),
            "confusion_matrix": {
                expected: dict(sorted(observed.items())) for expected, observed in sorted(confusion.items())
            },
        },
        "claim_boundary": {
            "official_CMS_outcome_scoring": True,
            "inferred_legal_ground_scoring": False,
            "complete_denial_package": False,
            "clinical_appropriateness": False,
            "full_appeal_evaluation": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--code-revision")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    try:
        output.relative_to(ROOT.resolve())
    except ValueError:
        raise ValueError(f"score report must be inside the repository: {output}") from None
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError("refusing to overwrite an outcome score report")
    report = score(args.benchmark, args.manifest, args.predictions, output, code_revision=args.code_revision)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
