#!/usr/bin/env python3
"""Interactive human-only annotator for an outcome-blinded CMS queue."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from appeal_evaluation import RationaleCategory, inspect_queue, route_for
from create_cms_qic_annotation_queues import load_object
from sample_cms_qic_benchmark import require_external


def read_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"queue row {line_number} must be an object")
            rows.append(value)
    return rows


def parse_span_spec(value: str) -> list[dict[str, object]]:
    spans: list[dict[str, object]] = []
    if not value.strip():
        return spans
    for part in value.split(","):
        pieces = part.strip().split(":")
        if len(pieces) != 2:
            raise ValueError("spans must use start:end[,start:end]")
        try:
            start, end = (int(piece.strip()) for piece in pieces)
        except ValueError as error:
            raise ValueError("span offsets must be integers") from error
        spans.append({"start": start, "end": end})
    return spans


def prompt_choice(prompt: str, choices: list[str]) -> int:
    print("\nChoose one:")
    for index, choice in enumerate(choices, start=1):
        print(f"  {index}. {choice}")
    while True:
        answer = input(prompt).strip()
        if answer.casefold() in {"q", "quit"}:
            raise KeyboardInterrupt
        try:
            index = int(answer)
        except ValueError:
            print("Enter one of the displayed numbers.")
            continue
        if 1 <= index <= len(choices):
            return index - 1
        print("That number is outside the displayed choices.")


def prompt_secondary(categories: list[RationaleCategory], primary: RationaleCategory) -> list[str]:
    available = [category for category in categories if category is not primary]
    choices = ", ".join(f"{index + 1}:{category.value}" for index, category in enumerate(available))
    while True:
        answer = input(f"Secondary categories ({choices}; blank for none): ").strip()
        if not answer:
            return []
        try:
            indexes = [int(value.strip()) - 1 for value in answer.split(",")]
        except ValueError:
            print("Use comma-separated choice numbers.")
            continue
        if any(index < 0 or index >= len(available) for index in indexes) or len(indexes) != len(set(indexes)):
            print("Choose distinct numbers from the displayed choices.")
            continue
        return [available[index].value for index in indexes]


def annotated_payload(row: dict[str, Any], categories: list[RationaleCategory]) -> dict[str, object]:
    context = row["context"]
    print("\n" + "=" * 88)
    print(f"Case {row['case_ref']} | split={row['split']}")
    for field in ("part", "appeal_type", "condition", "requested_item_or_drug"):
        print(f"{field}: {context.get(field, '')}")
    for field in ("decision_rationale", "policy_context"):
        text = context.get(field, "")
        print(f"\n{field} (offsets are Python/Unicode character positions):\n{text}")

    choices = [category.value for category in categories]
    category = categories[prompt_choice("Principal category number (insufficient_information abstains): ", choices)]
    if category is RationaleCategory.INSUFFICIENT_INFORMATION:
        return {
            "disposition": "abstained",
            "primary_category": category.value,
            "secondary_categories": [],
            "route": route_for(category).value,
            "rationale_spans": [],
            "policy_spans": [],
            "confidence": int(input("Confidence (1-5): ").strip()),
        }

    secondary = prompt_secondary(categories, category)
    while True:
        try:
            rationale_specs = parse_span_spec(input("Rationale spans (start:end; blank if none): "))
            policy_specs = parse_span_spec(input("Policy spans (start:end; blank if none): "))
            confidence = int(input("Confidence (1-5): ").strip())
            if not 1 <= confidence <= 5:
                raise ValueError("confidence must be from 1 to 5")
            break
        except ValueError as error:
            print(error)

    def with_hash(specs: list[dict[str, object]], field: str) -> list[dict[str, object]]:
        source_hash = row["source_hashes"][field]
        return [
            {"source_field": field, "start": spec["start"], "end": spec["end"], "source_sha256": source_hash}
            for spec in specs
        ]

    return {
        "disposition": "annotated",
        "primary_category": category.value,
        "secondary_categories": secondary,
        "route": route_for(category).value,
        "rationale_spans": with_hash(rationale_specs, "decision_rationale"),
        "policy_spans": with_hash(policy_specs, "policy_context"),
        "confidence": confidence,
    }


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(temporary, path)


def checkpoint(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    taxonomy_version: str,
    reviewer_id: str,
    reviewer_role: str,
) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        candidate = Path(handle.name)
    try:
        write_rows(candidate, rows)
        inspect_queue(
            candidate,
            taxonomy_version=taxonomy_version,
            annotator_id=reviewer_id,
            annotator_role=reviewer_role,
            require_locked_test=False,
        )
        os.replace(candidate, path)
    except Exception:
        candidate.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewer-role", required=True)
    parser.add_argument("--queue-key", choices=("reviewer_a", "reviewer_b"), required=True)
    parser.add_argument("--split", default="locked_test", choices=("development", "locked_test"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    source = require_external(args.input, "annotation queue")
    output = require_external(args.output, "filled annotation queue")
    if output.exists() and not args.resume:
        raise FileExistsError("filled queue exists; pass --resume to continue it")
    manifest = load_object(args.manifest, "annotation queue manifest")
    taxonomy = load_object(args.taxonomy, "annotation taxonomy")
    taxonomy_id = taxonomy.get("taxonomy_id")
    if not isinstance(taxonomy_id, str) or not taxonomy_id.strip():
        raise ValueError("taxonomy_id is required")
    expected = manifest.get("queues")
    if not isinstance(expected, dict):
        raise ValueError("annotation queue manifest lacks queue fingerprints")
    expected_queue = expected.get(args.queue_key)
    if not isinstance(expected_queue, dict):
        raise ValueError("annotation queue manifest lacks the selected queue")

    input_rows = read_rows(output if output.exists() else source)
    inspection = inspect_queue(
        output if output.exists() else source,
        taxonomy_version=taxonomy_id,
        annotator_id=args.reviewer_id,
        annotator_role=args.reviewer_role,
        require_locked_test=False,
    )
    if inspection.order_fingerprint != expected_queue.get("order_fingerprint"):
        raise ValueError("queue order or membership does not match the committed manifest")
    if inspection.context_fingerprint != expected_queue.get("context_fingerprint"):
        raise ValueError("queue source context does not match the committed manifest")
    if inspection.partial_count:
        raise ValueError("queue contains partial annotations; repair them before continuing")

    categories = list(RationaleCategory)
    changed = 0
    for index, row in enumerate(input_rows):
        if row.get("split") != args.split:
            continue
        annotation = row.get("annotation")
        if isinstance(annotation, dict) and annotation.get("confidence") is not None:
            continue
        try:
            row["annotation"] = annotated_payload(row, categories)
            row["review_meta"] = {
                "human_reviewed": True,
                "review_mode": "human_entered",
                "reviewer_id": args.reviewer_id,
                "reviewer_role": args.reviewer_role,
            }
            # Validate the row before checkpointing so a malformed span never
            # replaces the last valid checkpoint.
            checkpoint(
                output,
                input_rows,
                taxonomy_version=taxonomy_id,
                reviewer_id=args.reviewer_id,
                reviewer_role=args.reviewer_role,
            )
            changed += 1
            print(f"Saved case {index + 1}; {changed} new annotation(s) this run.")
        except (EOFError, KeyboardInterrupt):
            print("\nReview interrupted after the last valid checkpoint.")
            return 2
    print(f"Review complete for selected {args.split} rows: {changed} new annotation(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
