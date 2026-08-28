#!/usr/bin/env python3
"""Inspect an official CMS QIC bulk CSV without emitting source values.

The bulk file is kept outside the repository.  This inspector streams one CSV
row at a time, records schema and aggregate counts, hashes technical privacy
locators, and writes no source value or narrative text to its report.  A clean
technical scan is not a legal privacy or reuse decision.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fetch_cms_qic_summary import DATASET_IDS
from inspect_cms_qic import PART_C_FIELDS, PART_D_FIELDS, privacy_categories, text_value


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID = "cms_qic_decision_summaries"
EXPECTED_FIELDS = {
    "part_c": PART_C_FIELDS,
    "part_d": PART_D_FIELDS,
}
BULK_FIELD_ALIASES = {
    "Part": "part",
    "Decision_Date": "decision_date",
    "Decision_Date_Sortable": "decision_date_sortable",
    "Decision": "decision",
    "Appeal_Type": "appeal_type",
    "Condition": "_condition",
    "Item_Service": "item_service",
    "Drug": "drug",
    "Decision_Rationale": "decision_rationale",
    "Coverage_Rules": "coverage_rules",
    "Related_Reference_ID": "related_reference_id",
}
FIELD_ALIASES = {
    **{field: field for fields in EXPECTED_FIELDS.values() for field in fields},
    **BULK_FIELD_ALIASES,
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_outside_repository(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved
    raise ValueError(f"CMS QIC bulk input must be outside the repository: {resolved}")


def row_fingerprint(row: dict[str, str]) -> str:
    canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def source_reference_hash(part: str, record_number: str) -> str:
    return hashlib.sha256(
        f"{SOURCE_ID}:{part}:{record_number}".encode("utf-8")
    ).hexdigest()


def inspect(
    input_path: Path,
    *,
    part: str,
    source_url: str,
    source_etag: str | None,
    expected_record_count: int | None,
) -> dict[str, Any]:
    if part not in DATASET_IDS:
        raise ValueError(f"unknown CMS QIC part: {part}")
    if not source_url:
        raise ValueError("CMS QIC bulk source URL is required")
    if expected_record_count is not None and expected_record_count <= 0:
        raise ValueError("expected record count must be positive")

    resolved_input = require_outside_repository(input_path)
    if not resolved_input.is_file():
        raise FileNotFoundError(f"CMS QIC bulk input does not exist: {resolved_input}")
    initial_stat = resolved_input.stat()

    expected_fields = EXPECTED_FIELDS[part]
    headers: list[str] = []
    missing_expected_fields: list[str] = []
    unexpected_fields: list[str] = []
    field_mapping: dict[str, str] = {}
    nonempty_counts: Counter[str] = Counter()
    candidate_counts: Counter[str] = Counter()
    candidate_counts_by_field: dict[str, Counter[str]] = {}
    candidate_locators: list[dict[str, Any]] = []
    rows_scanned = 0
    well_formed_rows = 0
    malformed_rows = 0

    with resolved_input.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        try:
            headers = next(reader)
        except StopIteration:
            raise ValueError("CMS QIC bulk CSV is empty") from None
        if not headers or any(not field for field in headers):
            raise ValueError("CMS QIC bulk CSV has an empty header field")
        if len(headers) != len(set(headers)):
            raise ValueError("CMS QIC bulk CSV has duplicate header fields")

        for header in headers:
            canonical = FIELD_ALIASES.get(header)
            if canonical is not None:
                if canonical in field_mapping.values():
                    raise ValueError(
                        f"CMS QIC bulk CSV maps multiple headers to {canonical}"
                    )
                field_mapping[header] = canonical
        canonical_fields = set(field_mapping.values())
        missing_expected_fields = sorted(expected_fields - canonical_fields)
        unexpected_fields = sorted(set(headers) - set(field_mapping))
        record_source_field = next(
            (
                source_field
                for source_field, canonical in field_mapping.items()
                if canonical == "record_number"
            ),
            None,
        )

        for row_number, values in enumerate(reader, start=1):
            rows_scanned += 1
            if len(values) != len(headers):
                malformed_rows += 1
                continue
            well_formed_rows += 1
            row = dict(zip(headers, values, strict=True))
            row_hash: str | None = None
            record_hash: str | None = None
            for field, raw_value in row.items():
                value = text_value(raw_value)
                if value:
                    nonempty_counts[field] += 1
                categories = privacy_categories(value) if value else ()
                if not categories:
                    continue
                if row_hash is None:
                    row_hash = row_fingerprint(row)
                if record_hash is None and record_source_field is not None:
                    record_number = text_value(row[record_source_field])
                    if record_number:
                        record_hash = source_reference_hash(part, record_number)
                field_counts = candidate_counts_by_field.setdefault(field, Counter())
                for category in categories:
                    candidate_counts[category] += 1
                    field_counts[category] += 1
                candidate_locators.append(
                    {
                        "csv_data_row": row_number,
                        "field": field,
                        "categories": list(categories),
                        "source_record_ref_sha256": record_hash,
                        "source_row_sha256": row_hash,
                        "value_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                        "value_length": len(value),
                    }
                )

    final_stat = resolved_input.stat()
    if (initial_stat.st_size, initial_stat.st_mtime_ns) != (
        final_stat.st_size,
        final_stat.st_mtime_ns,
    ):
        raise RuntimeError("CMS QIC bulk input changed during inspection")

    count_matches = (
        expected_record_count is None or rows_scanned == expected_record_count
    )
    schema_valid = not missing_expected_fields and malformed_rows == 0 and count_matches
    if not schema_valid:
        status = "bulk_inspection_blocked_schema_or_count"
    elif candidate_locators:
        status = "privacy_candidates_require_human_review"
    else:
        status = "privacy_scan_complete_no_candidates"

    return {
        "schema_version": "0.1",
        "recorded_at": now_iso(),
        "status": status,
        "source_id": SOURCE_ID,
        "source": {
            "part": part,
            "dataset_id": DATASET_IDS[part],
            "source_url": source_url,
            "etag": source_etag or None,
            "raw_artifact_location": "outside_repository_only",
            "raw_rows_written": False,
        },
        "artifact": {
            "file_name": resolved_input.name,
            "bytes": final_stat.st_size,
            "sha256": sha256_file(resolved_input),
            "preserved_unchanged": True,
        },
        "inspection": {
            "csv_headers": headers,
            "expected_fields": sorted(expected_fields),
            "field_mapping": field_mapping,
            "missing_expected_fields": missing_expected_fields,
            "unexpected_fields": unexpected_fields,
            "rows_scanned": rows_scanned,
            "well_formed_rows": well_formed_rows,
            "malformed_rows": malformed_rows,
            "expected_record_count": expected_record_count,
            "record_count_matches_expected": count_matches,
            "nonempty_field_counts": dict(sorted(nonempty_counts.items())),
            "schema_valid": schema_valid,
        },
        "privacy_scan": {
            "candidate_counts": dict(sorted(candidate_counts.items())),
            "candidate_counts_by_field": {
                field: dict(sorted(counts.items()))
                for field, counts in sorted(candidate_counts_by_field.items())
            },
            "candidate_locator_count": len(candidate_locators),
            "technical_pattern_scan_only": True,
            "legal_determination_claimed": False,
        },
        "candidate_locators": candidate_locators,
        "human_review": {
            "required_before_full_extraction_acceptance": bool(candidate_locators),
            "raw_values_in_report": False,
            "decision_file": "outside_repository_only",
            "reviewer_identity": None,
            "review_status": "pending" if candidate_locators else "not_required_by_technical_scan",
        },
        "gates": {
            "schema": "pass" if schema_valid else "blocked",
            "privacy": "human_review_required" if candidate_locators else "technical_scan_clean",
            "reuse": "source_metadata_only_pending_source_specific_review",
            "prior_authorization": "not_verified",
        },
        "acceptance": {
            "accepted_for_local_evaluation": False,
            "accepted_record_count": 0,
            "narrative_rows_committed": False,
            "full_appeal_evaluation_allowed": False,
        },
        "evaluation": {
            "summary_cases_evaluated": 0,
            "full_appeal_cases_evaluated": 0,
            "regulator_ground_truth_comparisons": 0,
        },
    }


def write_report(report: dict[str, Any], output: Path) -> None:
    resolved_output = output.expanduser().resolve()
    if resolved_output.exists():
        raise FileExistsError(f"refusing to overwrite CMS QIC bulk report: {resolved_output}")
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=resolved_output.parent,
            prefix=f".{resolved_output.name}.",
            suffix=".partial",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(resolved_output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", choices=sorted(DATASET_IDS), required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--source-etag", default="")
    parser.add_argument("--expected-record-count", type=int)
    args = parser.parse_args()

    report = inspect(
        args.csv,
        part=args.part,
        source_url=args.source_url,
        source_etag=args.source_etag or None,
        expected_record_count=args.expected_record_count,
    )
    write_report(report, args.output)
    print(
        json.dumps(
            {
                "status": report["status"],
                "part": report["source"]["part"],
                "rows_scanned": report["inspection"]["rows_scanned"],
                "candidate_locator_count": report["privacy_scan"]["candidate_locator_count"],
                "sha256": report["artifact"]["sha256"],
                "output": str(args.output.expanduser().resolve()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
