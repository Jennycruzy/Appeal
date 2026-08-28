#!/usr/bin/env python3
"""Interactively review CMS QIC bulk privacy candidates.

Candidate values are read from the unchanged CSV and shown only in the
reviewer's terminal. The decision file contains hashes, categories, counts,
decisions, and reviewer metadata; it never contains a source value. The
decision file must remain outside the repository.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from inspect_cms_qic_bulk import row_fingerprint, sha256_file


ROOT = Path(__file__).resolve().parents[1]
DECISION_OPTIONS = {
    "f": "false_positive_public_context",
    "r": "remove_or_redact_before_use",
    "b": "confirmed_identifier_block",
    "l": "needs_legal_review",
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def require_external(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved
    raise ValueError(f"{label} must be outside the repository: {resolved}")


def candidate_groups(report: dict[str, Any]) -> list[dict[str, Any]]:
    locators = report.get("candidate_locators")
    if not isinstance(locators, list) or not locators:
        raise ValueError("CMS QIC bulk report has no candidate locators")
    groups: dict[str, dict[str, Any]] = {}
    for locator in locators:
        if not isinstance(locator, dict):
            raise ValueError("CMS QIC bulk privacy locator is not an object")
        value_hash = locator.get("value_sha256")
        if not isinstance(value_hash, str) or len(value_hash) != 64:
            raise ValueError("CMS QIC bulk privacy locator has an invalid value hash")
        field = locator.get("field")
        categories = locator.get("categories")
        row_number = locator.get("csv_data_row")
        if not isinstance(field, str) or not field:
            raise ValueError("CMS QIC bulk privacy locator has no field")
        if not isinstance(categories, list) or not all(isinstance(item, str) for item in categories):
            raise ValueError("CMS QIC bulk privacy locator has invalid categories")
        if not isinstance(row_number, int) or isinstance(row_number, bool) or row_number <= 0:
            raise ValueError("CMS QIC bulk privacy locator has an invalid row number")
        group = groups.setdefault(
            value_hash,
            {
                "value_sha256": value_hash,
                "value_length": locator.get("value_length"),
                "fields": set(),
                "match_types": set(),
                "occurrence_count": 0,
                "row_numbers": [],
                "locators": [],
            },
        )
        if group["value_length"] != locator.get("value_length"):
            raise ValueError("CMS QIC bulk privacy locator length mismatch")
        group["fields"].add(field)
        group["match_types"].update(categories)
        group["occurrence_count"] += 1
        group["row_numbers"].append(row_number)
        group["locators"].append(locator)

    result: list[dict[str, Any]] = []
    for value_hash in sorted(groups):
        group = groups[value_hash]
        result.append(
            {
                "value_sha256": group["value_sha256"],
                "value_length": group["value_length"],
                "fields": sorted(group["fields"]),
                "match_types": sorted(group["match_types"]),
                "occurrence_count": group["occurrence_count"],
                "row_numbers": sorted(group["row_numbers"]),
                "locators": group["locators"],
            }
        )
    return result


def load_candidate_values(
    csv_path: Path,
    candidates: list[dict[str, Any]],
) -> dict[str, str]:
    targets: dict[tuple[int, str], tuple[str, str]] = {}
    target_fields_by_row: dict[int, list[str]] = {}
    for candidate in candidates:
        value_hash = str(candidate["value_sha256"])
        for locator in candidate["locators"]:
            key = (int(locator["csv_data_row"]), str(locator["field"]))
            expected = (value_hash, str(locator["source_row_sha256"]))
            previous = targets.get(key)
            if previous is not None and previous != expected:
                raise ValueError(f"conflicting privacy locator at row {key[0]}, field {key[1]}")
            targets[key] = expected
            if previous is None:
                target_fields_by_row.setdefault(key[0], []).append(key[1])

    values: dict[str, str] = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        try:
            headers = next(reader)
        except StopIteration:
            raise ValueError("CMS QIC bulk CSV is empty") from None
        if len(headers) != len(set(headers)):
            raise ValueError("CMS QIC bulk CSV has duplicate header fields")
        for row_number, raw_values in enumerate(reader, start=1):
            if len(raw_values) != len(headers):
                raise ValueError(f"CMS QIC bulk CSV has a malformed row at {row_number}")
            row = dict(zip(headers, raw_values, strict=True))
            fields = target_fields_by_row.get(row_number, [])
            if not fields:
                continue
            row_hash = row_fingerprint(row)
            for field in fields:
                expected_hash, expected_row_hash = targets[(row_number, field)]
                if row_hash != expected_row_hash:
                    raise ValueError(f"CMS QIC bulk row hash mismatch at row {row_number}")
                value = row[field]
                actual_hash = hashlib.sha256(value.strip().encode("utf-8")).hexdigest()
                if actual_hash != expected_hash:
                    raise ValueError(f"CMS QIC bulk value hash mismatch at row {row_number}, field {field}")
                previous = values.get(expected_hash)
                if previous is not None and previous != value.strip():
                    raise ValueError("same privacy hash resolved to different values")
                values[expected_hash] = value.strip()

    missing = sorted(set(targets[key][0] for key in targets) - set(values))
    if missing:
        raise ValueError(f"CMS QIC bulk privacy locators were not found: {len(missing)}")
    return values


def write_decisions(
    output: Path,
    *,
    source: dict[str, Any],
    reviewer: str,
    candidates: list[dict[str, Any]],
    decisions: dict[str, str],
    status: str,
) -> None:
    counts: Counter[str] = Counter(decisions.values())
    report = {
        "schema_version": "0.1",
        "status": status,
        "source": source,
        "privacy_review": {
            "reviewer": reviewer,
            "reviewed_at": now_iso(),
            "candidate_record_count": len(candidates),
            "decision_count": len(decisions),
            "unresolved_count": len(candidates) - len(decisions),
            "decision_counts": dict(sorted(counts.items())),
            "raw_values_in_decision_file": False,
            "decisions": [
                {
                    "value_sha256": str(candidate["value_sha256"]),
                    "decision": decisions[str(candidate["value_sha256"])],
                    "match_types": candidate["match_types"],
                    "fields": candidate["fields"],
                    "occurrence_count": candidate["occurrence_count"],
                }
                for candidate in candidates
                if str(candidate["value_sha256"]) in decisions
            ],
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(output, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    csv_path = require_external(args.csv, "CMS QIC bulk CSV")
    report_path = args.report.expanduser().resolve()
    output = require_external(args.output, "CMS QIC privacy decision output")
    if not csv_path.is_file():
        raise FileNotFoundError(f"CMS QIC bulk CSV does not exist: {csv_path}")
    if not report_path.is_file():
        raise FileNotFoundError(f"CMS QIC bulk report does not exist: {report_path}")
    if output.exists() and not args.replace:
        raise FileExistsError(f"refusing to overwrite CMS QIC privacy decisions: {output}")

    report = load_json(report_path)
    artifact = report.get("artifact")
    source = report.get("source")
    inspection = report.get("inspection")
    if not isinstance(artifact, dict) or not isinstance(source, dict) or not isinstance(inspection, dict):
        raise ValueError("CMS QIC bulk report is missing source, artifact, or inspection metadata")
    expected_hash = artifact.get("sha256")
    actual_hash = sha256_file(csv_path)
    if actual_hash != expected_hash:
        raise ValueError(f"CMS QIC bulk CSV hash mismatch: expected {expected_hash}, got {actual_hash}")
    if inspection.get("schema_valid") is True:
        raise ValueError("privacy review is intended for a report whose acceptance gates are still closed")

    candidates = candidate_groups(report)
    candidate_values = load_candidate_values(csv_path, candidates)
    reviewer = str(args.reviewer).strip() or input("Reviewer identifier: ").strip()
    if not reviewer:
        raise ValueError("reviewer identifier is required")

    decisions: dict[str, str] = {}
    source_metadata = {
        "source_id": report.get("source_id"),
        "part": source.get("part"),
        "file_name": csv_path.name,
        "sha256": actual_hash,
        "report_file_name": report_path.name,
    }
    for index, candidate in enumerate(candidates, start=1):
        value_hash = str(candidate["value_sha256"])
        print(f"\nCandidate {index}/{len(candidates)}")
        print(f"Match types: {', '.join(candidate['match_types'])}")
        print(f"Fields: {', '.join(candidate['fields'])}")
        print(f"Occurrences: {candidate['occurrence_count']}")
        print("Value (terminal only): " + candidate_values[value_hash])
        while True:
            choice = input(
                "Decision [f=false positive, r=redact, b=block, l=legal review, q=quit]: "
            ).strip().lower()
            if choice == "q":
                write_decisions(
                    output,
                    source=source_metadata,
                    reviewer=reviewer,
                    candidates=candidates,
                    decisions=decisions,
                    status="partial",
                )
                print(f"Saved partial metadata-only review: {output}")
                return 0
            if choice in DECISION_OPTIONS:
                decisions[value_hash] = DECISION_OPTIONS[choice]
                break
            print("Choose f, r, b, l, or q.")

    write_decisions(
        output,
        source=source_metadata,
        reviewer=reviewer,
        candidates=candidates,
        decisions=decisions,
        status="complete",
    )
    print(f"Saved metadata-only privacy decisions: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
