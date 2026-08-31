#!/usr/bin/env python3
"""Convert an edited CMS review sheet into a validated reviewer queue."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from appeal_evaluation import RationaleCategory, inspect_queue, route_for
from create_cms_qic_annotation_queues import load_object
from sample_cms_qic_benchmark import require_external


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        values = [json.loads(line) for line in handle if line.strip()]
    if not all(isinstance(value, dict) for value in values):
        raise ValueError("queue contains a non-object row")
    return values


def parse_bool(value: str, label: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"{label} must be TRUE or FALSE")


def parse_spans(value: str, field: str, source_hash: str, label: str) -> list[dict[str, object]]:
    if not value.strip():
        return []
    result: list[dict[str, object]] = []
    for index, item in enumerate(value.split(",")):
        pieces = item.strip().split(":")
        if len(pieces) != 2:
            raise ValueError(f"{label}[{index}] must use start:end")
        try:
            start, end = (int(piece.strip()) for piece in pieces)
        except ValueError as error:
            raise ValueError(f"{label}[{index}] offsets must be integers") from error
        result.append({"source_field": field, "start": start, "end": end, "source_sha256": source_hash})
    return result


def parse_annotation(row: dict[str, str]) -> dict[str, object]:
    category = row["primary_category"].strip()
    try:
        category_enum = RationaleCategory(category)
    except ValueError as error:
        raise ValueError(f"unsupported primary category: {category}") from error
    secondary = [value.strip() for value in row["secondary_categories"].split(",") if value.strip()]
    for value in secondary:
        RationaleCategory(value)
    route = row["route"].strip()
    if route != route_for(category_enum).value:
        raise ValueError(f"route does not match primary category {category}")
    confidence = int(row["confidence"].strip())
    disposition = row["disposition"].strip()
    if disposition not in {"annotated", "abstained"}:
        raise ValueError(f"unsupported disposition: {disposition}")
    if category_enum is RationaleCategory.INSUFFICIENT_INFORMATION and disposition != "abstained":
        raise ValueError("insufficient_information must be abstained")
    if category_enum is not RationaleCategory.INSUFFICIENT_INFORMATION and disposition != "annotated":
        raise ValueError("only insufficient_information may be abstained")
    return {
        "disposition": disposition,
        "primary_category": category,
        "secondary_categories": secondary,
        "route": route,
        "rationale_spans": parse_spans(row["rationale_spans"], "decision_rationale", row["rationale_source_sha256"].strip(), "rationale_spans"),
        "policy_spans": parse_spans(row["policy_spans"], "policy_context", row["policy_source_sha256"].strip(), "policy_spans"),
        "confidence": confidence,
    }


def import_sheet(
    queue_path: Path,
    sheet_path: Path,
    manifest_path: Path,
    taxonomy_path: Path,
    output_path: Path,
    *,
    reviewer_id: str,
    reviewer_role: str,
) -> dict[str, object]:
    queue_path = require_external(queue_path, "source queue")
    sheet_path = require_external(sheet_path, "edited review sheet")
    output_path = require_external(output_path, "filled queue output")
    if output_path.exists():
        raise FileExistsError("filled queue output already exists")
    manifest = load_object(manifest_path, "annotation queue manifest")
    taxonomy = load_object(taxonomy_path, "annotation taxonomy")
    taxonomy_id = taxonomy.get("taxonomy_id")
    expected = manifest.get("queues")
    if not isinstance(taxonomy_id, str) or not isinstance(expected, dict) or not isinstance(expected.get("reviewer_a"), dict):
        raise ValueError("taxonomy or queue manifest is incomplete")
    original_rows = read_rows(queue_path)
    inspection = inspect_queue(
        queue_path,
        taxonomy_version=taxonomy_id,
        annotator_id=reviewer_id,
        annotator_role=reviewer_role,
        require_locked_test=False,
    )
    expected_a = expected["reviewer_a"]
    if inspection.order_fingerprint != expected_a.get("order_fingerprint") or inspection.context_fingerprint != expected_a.get("context_fingerprint"):
        raise ValueError("source queue identity does not match the committed manifest")
    by_case = {row["case_ref"]: row for row in original_rows}
    seen: set[str] = set()
    edited: dict[str, dict[str, str]] = {}
    required_columns = {
        "case_ref", "split", "part", "appeal_type", "condition", "requested_item_or_drug",
        "decision_rationale", "policy_context", "rationale_source_sha256", "policy_source_sha256",
        "disposition", "primary_category", "secondary_categories", "route", "rationale_spans",
        "policy_spans", "confidence", "human_reviewed",
    }
    with sheet_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
            raise ValueError("review sheet is missing required columns")
        for line_number, raw in enumerate(reader, start=2):
            row = {key: value or "" for key, value in raw.items() if key is not None}
            case_ref = row["case_ref"].strip()
            if case_ref in seen:
                raise ValueError(f"duplicate sheet case_ref on row {line_number}")
            seen.add(case_ref)
            if row["split"].strip() != "locked_test":
                raise ValueError(f"sheet row {line_number} is not locked_test")
            original = by_case.get(case_ref)
            if original is None:
                raise ValueError(f"sheet row {line_number} is not in reviewer A queue")
            context = original["context"]
            hashes = original["source_hashes"]
            checks = {
                "part": context.get("part", ""),
                "appeal_type": context.get("appeal_type", ""),
                "condition": context.get("condition", ""),
                "requested_item_or_drug": context.get("requested_item_or_drug", ""),
                "decision_rationale": context.get("decision_rationale", ""),
                "policy_context": context.get("policy_context", ""),
                "rationale_source_sha256": hashes.get("decision_rationale", ""),
                "policy_source_sha256": hashes.get("policy_context", ""),
            }
            for key, expected_value in checks.items():
                if row[key] != str(expected_value):
                    raise ValueError(f"sheet row {line_number} changed protected field {key}")
            if not parse_bool(row["human_reviewed"], f"sheet row {line_number}.human_reviewed"):
                raise ValueError(f"sheet row {line_number} is not marked human_reviewed")
            parse_annotation(row)
            edited[case_ref] = row
    locked_refs = {row["case_ref"] for row in original_rows if row.get("split") == "locked_test"}
    if seen != locked_refs:
        raise ValueError("review sheet must contain exactly all 100 locked_test cases")

    output_rows: list[dict[str, Any]] = []
    for original in original_rows:
        copy = dict(original)
        case_ref = str(original["case_ref"])
        if case_ref in edited:
            row = edited[case_ref]
            copy["annotation"] = parse_annotation(row)
            copy["review_meta"] = {
                "human_reviewed": True,
                "review_mode": "human_reviewed_assistant_proposal",
                "proposal_source": row.get("proposal_source", "appeal-rationale-cue-review-v1"),
                "reviewer_id": reviewer_id,
                "reviewer_role": reviewer_role,
            }
        output_rows.append(copy)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as handle:
        for row in output_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    validated = inspect_queue(
        output_path,
        taxonomy_version=taxonomy_id,
        annotator_id=reviewer_id,
        annotator_role=reviewer_role,
        require_locked_test=False,
    )
    locked_validated = [row for row in validated.rows if row.split == "locked_test"]
    if len(locked_validated) != 100 or any(row.annotation is None or not row.human_reviewed for row in locked_validated):
        raise ValueError("converted queue did not pass complete locked-test human-review validation")
    return {
        "status": "cms_qic_human_reviewed_queue_ready",
        "queue_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "locked_test_rows": len(edited),
        "human_reviewed_rows": len(edited),
        "outcomes_in_output": False,
        "review_mode": "human_reviewed_assistant_proposal",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--sheet", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewer-role", required=True)
    args = parser.parse_args()
    print(json.dumps(import_sheet(
        args.queue,
        args.sheet,
        args.manifest,
        args.taxonomy,
        args.output,
        reviewer_id=args.reviewer_id,
        reviewer_role=args.reviewer_role,
    ), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
