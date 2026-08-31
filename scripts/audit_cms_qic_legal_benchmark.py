#!/usr/bin/env python3
"""Audit the screened CMS legal-ground sample without emitting case text."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from inspect_cms_qic import privacy_categories
from inspect_cms_qic_bulk import sha256_file
from sample_cms_qic_benchmark import require_external
from score_cms_qic_outcomes import benchmark_outcomes, read_jsonl


ROOT = Path(__file__).resolve().parents[1]


def audit(benchmark_path: Path, manifest_path: Path) -> dict[str, Any]:
    benchmark_path = require_external(benchmark_path, "CMS legal-ground benchmark")
    outcomes, manifest, benchmark_hash = benchmark_outcomes(benchmark_path, manifest_path)
    split_counts: Counter[str] = Counter()
    privacy_counts: Counter[str] = Counter()
    empty_rationale = 0
    empty_policy = 0
    case_digest = hashlib.sha256()
    for index, row in enumerate(read_jsonl(benchmark_path, "benchmark"), start=1):
        reference = row.get("case_ref")
        split = row.get("split")
        model_input = row.get("model_input")
        if not isinstance(reference, str) or not isinstance(split, str) or not isinstance(model_input, dict):
            raise ValueError(f"benchmark row {index} is incomplete")
        if "regulator_outcome" in model_input or "hidden_labels" in model_input:
            raise ValueError(f"benchmark row {index} exposes an outcome in model_input")
        rationale = model_input.get("decision_rationale")
        policy = model_input.get("policy_context")
        if not isinstance(rationale, str) or not rationale.strip():
            empty_rationale += 1
        if not isinstance(policy, str) or not policy.strip():
            empty_policy += 1
        for value in model_input.values():
            if isinstance(value, str):
                privacy_counts.update(privacy_categories(value))
        split_counts[split] += 1
        case_digest.update(reference.encode("ascii"))
        case_digest.update(b"\n")
    if empty_rationale or empty_policy or privacy_counts:
        raise ValueError("screened legal-ground benchmark contains an ineligible row")
    expected_split_counts = manifest["sampling"]["split_counts"]
    if dict(sorted(split_counts.items())) != expected_split_counts:
        raise ValueError("benchmark split counts do not match manifest")
    return {
        "schema_version": "1.0",
        "status": "cms_qic_legal_ground_benchmark_audit_ready",
        "source": {
            "benchmark_sha256": benchmark_hash,
            "benchmark_manifest_sha256": sha256_file(manifest_path),
            "sample_count": sum(split_counts.values()),
            "locked_test_count": len(outcomes),
            "split_counts": dict(sorted(split_counts.items())),
            "case_identity_sha256": case_digest.hexdigest(),
        },
        "screen_audit": {
            "empty_rationale_rows": empty_rationale,
            "empty_policy_rows": empty_policy,
            "privacy_candidate_counts": dict(sorted(privacy_counts.items())),
            "privacy_detector": "technical_patterns_plus_person_name_context",
            "outcome_hidden_from_model_input": True,
            "raw_values_in_report": False,
        },
        "claim_boundary": {
            "official_CMS_outcome_track_available": True,
            "human_legal_ground_gold_available": False,
            "complete_denial_package": False,
            "full_appeal_evaluation": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    try:
        output.relative_to(ROOT.resolve())
    except ValueError:
        raise ValueError(f"audit report must be inside the repository: {output}") from None
    if output.exists():
        raise FileExistsError("refusing to overwrite a legal-ground audit report")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = audit(args.benchmark, args.manifest)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
