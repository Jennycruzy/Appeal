#!/usr/bin/env python3
"""Validate progress of blinded CMS human-review queues without revealing labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from appeal_evaluation import annotation_status, inspect_queue
from create_cms_qic_annotation_queues import load_object
from sample_cms_qic_benchmark import require_external
from inspect_cms_qic_bulk import sha256_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-a", type=Path, required=True)
    parser.add_argument("--queue-b", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviewer-a-id", required=True)
    parser.add_argument("--reviewer-a-role", required=True)
    parser.add_argument("--reviewer-b-id", required=True)
    parser.add_argument("--reviewer-b-role", required=True)
    args = parser.parse_args()

    queue_a = require_external(args.queue_a, "annotation queue A")
    queue_b = require_external(args.queue_b, "annotation queue B")
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
    report = annotation_status(
        inspection_a,
        inspection_b,
        taxonomy_version=taxonomy_id,
        adjudication_path=None,
    )
    report["manifest_sha256"] = sha256_file(args.manifest)
    report["taxonomy_sha256"] = sha256_file(args.taxonomy)
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(output)}, indent=2))
    return 0


def _verify_identity(inspection: Any, expected: dict[str, Any], label: str) -> None:
    if expected.get("order_fingerprint") != inspection.order_fingerprint:
        raise ValueError(f"{label} case order or membership does not match the committed manifest")
    if expected.get("context_fingerprint") != inspection.context_fingerprint:
        raise ValueError(f"{label} source context does not match the committed manifest")


if __name__ == "__main__":
    raise SystemExit(main())
