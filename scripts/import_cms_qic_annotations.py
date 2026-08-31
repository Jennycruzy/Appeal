#!/usr/bin/env python3
"""Build locked-test CMS gold labels from two blinded reviews and adjudications."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from appeal_evaluation import build_gold_labels, gold_to_json, inspect_queue
from create_cms_qic_annotation_queues import load_object
from inspect_cms_qic_bulk import sha256_file
from sample_cms_qic_benchmark import require_external


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-a", type=Path, required=True)
    parser.add_argument("--queue-b", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--reviewer-a-id", required=True)
    parser.add_argument("--reviewer-a-role", required=True)
    parser.add_argument("--reviewer-b-id", required=True)
    parser.add_argument("--reviewer-b-role", required=True)
    parser.add_argument("--adjudication", type=Path)
    parser.add_argument("--adjudicator-id")
    parser.add_argument("--adjudicator-role")
    parser.add_argument("--gold-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()

    queue_a = require_external(args.queue_a, "annotation queue A")
    queue_b = require_external(args.queue_b, "annotation queue B")
    gold_output = require_external(args.gold_output, "gold output")
    if gold_output.exists():
        raise FileExistsError("refusing to overwrite an existing gold output")
    if args.adjudication is not None:
        adjudication = require_external(args.adjudication, "adjudication file")
    else:
        adjudication = None
    manifest = load_object(args.manifest, "annotation queue manifest")
    taxonomy = load_object(args.taxonomy, "annotation taxonomy")
    taxonomy_id = taxonomy.get("taxonomy_id")
    if not isinstance(taxonomy_id, str) or not taxonomy_id.strip():
        raise ValueError("taxonomy_id is required")
    expected_queues = manifest.get("queues")
    if not isinstance(expected_queues, dict):
        raise ValueError("annotation queue manifest lacks queues")
    expected_a = expected_queues.get("reviewer_a")
    expected_b = expected_queues.get("reviewer_b")
    if not isinstance(expected_a, dict) or not isinstance(expected_b, dict):
        raise ValueError("annotation queue manifest lacks queue fingerprints")
    if args.reviewer_a_id == args.reviewer_b_id:
        raise ValueError("independent reviewer IDs must differ")

    inspection_a = inspect_queue(
        queue_a,
        taxonomy_version=taxonomy_id,
        annotator_id=args.reviewer_a_id,
        annotator_role=args.reviewer_a_role,
        require_locked_test=False,
    )
    inspection_b = inspect_queue(
        queue_b,
        taxonomy_version=taxonomy_id,
        annotator_id=args.reviewer_b_id,
        annotator_role=args.reviewer_b_role,
        require_locked_test=False,
    )
    _verify_identity(inspection_a, expected_a, "queue A")
    _verify_identity(inspection_b, expected_b, "queue B")
    gold = build_gold_labels(
        inspection_a,
        inspection_b,
        adjudication_path=adjudication,
        taxonomy_version=taxonomy_id,
        adjudicator_id=args.adjudicator_id,
        adjudicator_role=args.adjudicator_role,
    )
    gold_output.parent.mkdir(parents=True, exist_ok=True)
    with gold_output.open("x", encoding="utf-8") as handle:
        for label in gold:
            handle.write(json.dumps(gold_to_json(label), ensure_ascii=False, sort_keys=True) + "\n")

    resolutions = Counter(label.resolution.value for label in gold)
    report = {
        "schema_version": "1.0",
        "status": "cms_qic_locked_test_gold_labels_ready",
        "gold_claim_allowed": True,
        "source": {
            "taxonomy_id": taxonomy_id,
            "taxonomy_sha256": sha256_file(args.taxonomy),
            "queue_a_sha256": inspection_a.sha256,
            "queue_b_sha256": inspection_b.sha256,
            "adjudication_sha256": sha256_file(adjudication) if adjudication is not None else None,
            "locked_test_count": len(gold),
            "source_narratives_emitted": False,
            "outcome_labels_in_review_inputs": False,
        },
        "review": {
            "reviewer_a_id": args.reviewer_a_id,
            "reviewer_b_id": args.reviewer_b_id,
            "adjudicator_id": args.adjudicator_id,
            "resolution_counts": dict(sorted(resolutions.items())),
            "disagreement_count": resolutions.get("adjudicated", 0),
            "minimum_independent_annotations": 2,
            "third_human_required_for_disagreement": True,
            "model_generated_label_can_be_gold": False,
        },
        "gold_output": {
            "location": "outside_repository_only",
            "sha256": sha256_file(gold_output),
            "line_count": len(gold),
        },
        "reproducibility": {
            "gold_output_content_sha256": hashlib.sha256(gold_output.read_bytes()).hexdigest(),
            "labels_are_case_ref_and_source_span_based": True,
        },
    }
    report_output = args.report_output.expanduser().resolve()
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(report_output), "gold": str(gold_output)}, indent=2))
    return 0


def _verify_identity(inspection: object, expected: dict[str, object], label: str) -> None:
    order_fingerprint = getattr(inspection, "order_fingerprint", None)
    context_fingerprint = getattr(inspection, "context_fingerprint", None)
    if expected.get("order_fingerprint") != order_fingerprint:
        raise ValueError(f"{label} case order or membership does not match the committed manifest")
    if expected.get("context_fingerprint") != context_fingerprint:
        raise ValueError(f"{label} source context does not match the committed manifest")


if __name__ == "__main__":
    raise SystemExit(main())
