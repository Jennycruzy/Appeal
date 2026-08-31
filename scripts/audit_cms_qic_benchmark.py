#!/usr/bin/env python3
"""Audit CMS QIC benchmark leakage and run deterministic locked-test baselines."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from appeal_evaluation import wilson_interval
from inspect_cms_qic_bulk import sha256_file
from sample_cms_qic_benchmark import require_external


OUTCOME_CUES: dict[str, tuple[str, ...]] = {
    "favorable": (
        "we agree with you",
        "the plan must cover",
        "should be covered",
        "our decision is favorable",
    ),
    "partially favorable": (
        "partially favorable",
        "partly in your favor",
    ),
    "unfavorable": (
        "we agree with the plan",
        "the plan was correct",
        "does not have to cover",
        "our decision is unfavorable",
    ),
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("status") != "cms_qic_benchmark_sample_ready":
        raise ValueError("benchmark sample manifest is not ready")
    return value


def records(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"benchmark record {index} is not an object")
            yield value


def text_blob(model_input: dict[str, Any]) -> str:
    return " ".join(str(value) for value in model_input.values() if isinstance(value, str)).casefold()


def keyword_outcome(model_input: dict[str, Any]) -> str | None:
    blob = text_blob(model_input)
    matches = [outcome for outcome, cues in OUTCOME_CUES.items() if any(cue in blob for cue in cues)]
    return matches[0] if len(matches) == 1 else None


def normalize_label(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("hidden label must be a non-empty string")
    return " ".join(value.split()).casefold()


def accuracy(correct: int, total: int) -> dict[str, object]:
    if total == 0:
        return {"value": None, "numerator": 0, "denominator": 0, "confidence_95": None}
    low, high = wilson_interval(correct, total)
    return {
        "value": correct / total,
        "numerator": correct,
        "denominator": total,
        "confidence_95": [low, high],
    }


def audit(input_path: Path, manifest_path: Path) -> dict[str, object]:
    input_path = require_external(input_path, "CMS QIC benchmark input")
    manifest = load_manifest(manifest_path)
    artifact = manifest.get("artifact")
    sampling = manifest.get("sampling")
    if not isinstance(artifact, dict) or not isinstance(sampling, dict):
        raise ValueError("benchmark manifest is incomplete")
    if sha256_file(input_path) != artifact.get("sha256"):
        raise ValueError("benchmark input hash does not match its manifest")

    split_counts: Counter[str] = Counter()
    development_outcomes: Counter[str] = Counter()
    locked: list[tuple[dict[str, Any], dict[str, Any]]] = []
    direct_key_leaks: Counter[str] = Counter()
    exact_value_leaks: Counter[str] = Counter()
    seen_case_refs: set[str] = set()
    sample_digest = hashlib.sha256()
    for record in records(input_path):
        case_ref = record.get("case_ref")
        split = record.get("split")
        model_input = record.get("model_input")
        labels = record.get("hidden_labels")
        if not isinstance(case_ref, str) or len(case_ref) != 64 or case_ref in seen_case_refs:
            raise ValueError("benchmark case_ref must be a unique SHA-256")
        if split not in {"development", "locked_test"}:
            raise ValueError("benchmark split is invalid")
        if not isinstance(model_input, dict) or not isinstance(labels, dict):
            raise ValueError("benchmark record lacks model_input or hidden_labels")
        seen_case_refs.add(case_ref)
        sample_digest.update(case_ref.encode("ascii"))
        sample_digest.update(b"\n")
        split_counts[split] += 1
        for target in ("regulator_outcome", "appeal_type", "requested_item_class"):
            if target in model_input:
                direct_key_leaks[target] += 1
            label = labels.get(target)
            if isinstance(label, str) and label.strip() and normalize_label(label) in text_blob(model_input):
                exact_value_leaks[target] += 1
        outcome = normalize_label(labels.get("regulator_outcome"))
        if split == "development":
            development_outcomes[outcome] += 1
        else:
            locked.append((model_input, labels))

    expected_splits = sampling.get("split_counts")
    if dict(sorted(split_counts.items())) != expected_splits:
        raise ValueError("observed split counts do not match benchmark manifest")
    expected_identity = sampling.get("sample_identity_sha256")
    # The benchmark file is sorted by case_ref, so this reproduces the sample identity.
    if sample_digest.hexdigest() != expected_identity:
        raise ValueError("benchmark sample identity does not match manifest")
    if not development_outcomes:
        raise ValueError("development split has no outcome labels")
    majority_outcome = sorted(development_outcomes, key=lambda item: (-development_outcomes[item], item))[0]

    majority_correct = 0
    keyword_correct = 0
    keyword_total = 0
    appeal_type_correct = 0
    requested_class_correct = 0
    for model_input, labels in locked:
        gold_outcome = normalize_label(labels.get("regulator_outcome"))
        majority_correct += majority_outcome == gold_outcome
        keyword = keyword_outcome(model_input)
        if keyword is not None:
            keyword_total += 1
            keyword_correct += keyword == gold_outcome
        appeal_type_correct += normalize_label(model_input.get("appeal_type")) == normalize_label(labels.get("appeal_type"))
        requested_class_correct += normalize_label(model_input.get("part")) == "part d-drug"

    count = len(seen_case_refs)
    return {
        "schema_version": "1.0",
        "status": "cms_qic_leakage_and_baselines_complete",
        "recorded_at": now_iso(),
        "source": {
            "source_id": "cms_qic_decision_summaries",
            "source_class": "regulator_summary",
            "sample_count": count,
            "development_count": split_counts["development"],
            "locked_test_count": split_counts["locked_test"],
            "input_sha256": artifact.get("sha256"),
            "narratives_emitted": False,
        },
        "leakage_audit": {
            "direct_target_key_counts": dict(sorted(direct_key_leaks.items())),
            "exact_target_value_in_input_counts": dict(sorted(exact_value_leaks.items())),
            "interpretation": {
                "appeal_type": "explicit source-field extraction; not a reasoning-quality metric",
                "requested_item_class": "implied directly by the Part D dataset schema; not a reasoning-quality metric",
                "regulator_outcome": "target key is withheld, but rationale can contain outcome cues; report prediction only as exploratory",
                "coverage_rules": "grounding metric requires a separately annotated citation gold set",
            },
        },
        "baselines": {
            "development_majority_outcome": {
                "selected_label": majority_outcome,
                "development_label_counts": dict(sorted(development_outcomes.items())),
                "locked_test_selective_accuracy": accuracy(majority_correct, len(locked)),
            },
            "keyword_outcome": {
                "locked_test_selective_accuracy": accuracy(keyword_correct, keyword_total),
                "abstentions": len(locked) - keyword_total,
                "coverage": keyword_total / len(locked) if locked else 0.0,
            },
            "explicit_appeal_type_passthrough": {
                "locked_test_accuracy": accuracy(appeal_type_correct, len(locked)),
                "quality_claim_allowed": False,
            },
            "part_d_requested_item_class": {
                "locked_test_accuracy": accuracy(requested_class_correct, len(locked)),
                "quality_claim_allowed": False,
            },
        },
        "eligible_next_metrics": [
            "coverage-rule citation grounding after annotation",
            "rationale-category classification after independent label policy",
            "route recommendation against a predeclared operational mapping",
            "exploratory regulator-outcome prediction with leakage-stratified reporting",
        ],
        "claim_boundary": {
            "full_appeal_evaluation": False,
            "clinical_efficacy": False,
            "real_world_regulator_summary_benchmark": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.input, args.manifest)
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
