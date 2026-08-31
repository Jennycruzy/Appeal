#!/usr/bin/env python3
"""Create a blank, outcome-blinded spreadsheet for direct human annotation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from appeal_evaluation import inspect_queue
from create_cms_qic_annotation_queues import load_object
from sample_cms_qic_benchmark import require_external


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("queue contains a non-object row")
    return rows


def create_sheet(
    queue_path: Path,
    manifest_path: Path,
    taxonomy_path: Path,
    output: Path,
    *,
    queue_key: str,
) -> dict[str, object]:
    queue_path = require_external(queue_path, "annotation queue")
    output = require_external(output, "human review sheet")
    if output.exists():
        raise FileExistsError("human review sheet already exists")
    manifest = load_object(manifest_path, "annotation queue manifest")
    taxonomy = load_object(taxonomy_path, "annotation taxonomy")
    taxonomy_id = taxonomy.get("taxonomy_id")
    queues = manifest.get("queues")
    expected = queues.get(queue_key) if isinstance(queues, dict) else None
    if not isinstance(taxonomy_id, str) or not isinstance(expected, dict):
        raise ValueError("taxonomy or selected queue manifest entry is incomplete")

    inspection = inspect_queue(
        queue_path,
        taxonomy_version=taxonomy_id,
        annotator_id=f"{queue_key}-sheet",
        annotator_role="researcher",
        require_locked_test=False,
    )
    if inspection.order_fingerprint != expected.get("order_fingerprint") or inspection.context_fingerprint != expected.get("context_fingerprint"):
        raise ValueError("queue identity does not match the committed manifest")
    rows = [row for row in read_rows(queue_path) if row.get("split") == "locked_test"]
    if not rows:
        raise ValueError("queue has no locked_test rows")

    columns = [
        "case_ref", "split", "part", "appeal_type", "condition", "requested_item_or_drug",
        "decision_rationale", "policy_context", "rationale_source_sha256", "policy_source_sha256",
        "disposition", "primary_category", "secondary_categories", "route", "holding_spans",
        "policy_spans", "confidence", "human_reviewed", "review_note",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            context = row["context"]
            hashes = row["source_hashes"]
            writer.writerow({
                "case_ref": row["case_ref"],
                "split": row["split"],
                "part": context.get("part", ""),
                "appeal_type": context.get("appeal_type", ""),
                "condition": context.get("condition", ""),
                "requested_item_or_drug": context.get("requested_item_or_drug", ""),
                "decision_rationale": context.get("decision_rationale", ""),
                "policy_context": context.get("policy_context", ""),
                "rationale_source_sha256": hashes.get("decision_rationale", ""),
                "policy_source_sha256": hashes.get("policy_context", ""),
                "disposition": "",
                "primary_category": "",
                "secondary_categories": "",
                "route": "",
                "holding_spans": "",
                "policy_spans": "",
                "confidence": "",
                "human_reviewed": "FALSE",
                "review_note": "",
            })
    return {
        "status": "cms_qic_direct_human_review_sheet_ready",
        "queue_key": queue_key,
        "queue_sha256": inspection.sha256,
        "sheet_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "locked_test_rows": len(rows),
        "outcomes_in_sheet": False,
        "labels_prefilled": False,
        "direct_human_entry_required": True,
        "holding_span_definition": "shortest source sentence or contiguous sentences stating the operative holding; exclude framing and generic boilerplate",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--queue-key", choices=("reviewer_a", "reviewer_b"), required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(create_sheet(
        args.queue,
        args.manifest,
        args.taxonomy,
        args.output,
        queue_key=args.queue_key,
    ), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
