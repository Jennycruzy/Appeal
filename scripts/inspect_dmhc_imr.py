#!/usr/bin/env python3
"""Inspect the DMHC IMR CSV without emitting case text or identifiers."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "case_reference": ("case number", "case id", "imr case number", "imr number"),
    "regulator_outcome": ("determination", "decision", "outcome"),
    "denial_reason": ("denial reason", "reason for denial", "denial"),
    "treatment": ("treatment", "service", "procedure", "request"),
    "findings": ("findings", "finding", "rationale", "clinical", "summary"),
}

EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(
    r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}(?!\d)"
)
SSN = re.compile(r"\d{3}-\d{2}-\d{4}")
MEMBER_ID = re.compile(r"member\s*(?:id|number|no\.?|#)", re.I)
DOB = re.compile(r"(?:date\s+of\s+birth|\bDOB\b)", re.I)
ADDRESS = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9][A-Za-z0-9.'-]*"
    r"(?:\s+[A-Za-z0-9][A-Za-z0-9.'-]*){0,3}\s+"
    r"(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|"
    r"lane|ln|court|ct|way|highway|hwy)\b",
    re.I,
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def resolve_fields(headers: list[str]) -> dict[str, str | None]:
    normalized = {header: normalize_header(header) for header in headers}
    resolved: dict[str, str | None] = {}
    for field, aliases in FIELD_ALIASES.items():
        resolved[field] = next(
            (
                header
                for header, candidate in normalized.items()
                if any(alias in candidate for alias in aliases)
            ),
            None,
        )
    return resolved


def privacy_matches(values_by_field: dict[str, set[str]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    by_field: dict[str, dict[str, int]] = {}
    for field, values in sorted(values_by_field.items()):
        field_counts: Counter[str] = Counter()
        for value in values:
            if EMAIL.search(value):
                field_counts["email_shape"] += 1
            if PHONE.search(value):
                field_counts["phone_shape"] += 1
            if SSN.search(value):
                field_counts["ssn_shape"] += 1
            if MEMBER_ID.search(value):
                field_counts["member_id_label"] += 1
            if DOB.search(value):
                field_counts["date_of_birth_label"] += 1
            if ADDRESS.search(value):
                field_counts["physical_address_shape"] += 1
        if field_counts:
            by_field[field] = dict(sorted(field_counts.items()))
            counts.update(field_counts)
    return {
        "distinct_field_values_scanned": sum(len(values) for values in values_by_field.values()),
        "candidate_counts": dict(sorted(counts.items())),
        "candidate_counts_by_field": by_field,
        "status": "technical_pattern_scan_only_no_legal_determination_claimed",
    }


def read_csv(path: Path) -> dict[str, Any]:
    nonempty_counts: Counter[str] = Counter()
    distinct_values: dict[str, set[str]] = {}
    outcome_nonempty = 0
    outcome_values: set[str] = set()
    rows = 0
    nonempty_rows = 0
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or any(field is None for field in reader.fieldnames):
            raise ValueError("CSV does not contain a complete header row")
        headers = [field for field in reader.fieldnames]
        resolved = resolve_fields(headers)
        outcome_field = resolved["regulator_outcome"]
        for raw_row in reader:
            rows += 1
            row = {header: raw_row.get(header, "").strip() for header in headers}
            if any(row.values()):
                nonempty_rows += 1
            for header, value in row.items():
                if not value:
                    continue
                nonempty_counts[header] += 1
                distinct_values.setdefault(header, set()).add(value)
            if outcome_field is not None and row[outcome_field]:
                outcome_nonempty += 1
                outcome_values.add(row[outcome_field])
    return {
        "headers": headers,
        "resolved_fields": resolved,
        "rows": rows,
        "nonempty_rows": nonempty_rows,
        "nonempty_counts": dict(sorted(nonempty_counts.items())),
        "distinct_counts": {
            header: len(distinct_values.get(header, set())) for header in headers
        },
        "outcome_field": outcome_field,
        "outcome_nonempty": outcome_nonempty,
        "outcome_distinct_count": len(outcome_values),
        "privacy": privacy_matches(distinct_values),
    }


def inspect(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    inspection = read_csv(path)
    resolved = inspection["resolved_fields"]
    return {
        "schema_version": "0.1",
        "recorded_at": now_iso(),
        "status": "public_source_inspected_local_only_pending_acceptance",
        "artifact": {
            "source_id": "california_dmhc_imr_determinations",
            "publisher": "California Department of Managed Health Care",
            "catalog_url": "https://lab.data.ca.gov/dataset/independent-medical-review-imr-determinations-trend",
            "csv_url": "https://data.chhs.ca.gov/dataset/b79b3447-4c10-4ae6-84e2-1076f83bb24e/resource/3340c5d7-4054-4d03-90e0-5f44290ed095/download/independent-medical-review-determinations-trends.csv",
            "file_name": path.name,
            "retrieval_method": "manual_or_authorized_download",
            "local_file_size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "raw_artifact_location": "local_download_only_not_repo",
            "transformation": "none",
        },
        "inspection": {
            "data_rows": inspection["rows"],
            "nonempty_data_rows": inspection["nonempty_rows"],
            "columns": len(inspection["headers"]),
            "headers": inspection["headers"],
            "resolved_fields": resolved,
            "nonempty_counts": inspection["nonempty_counts"],
            "distinct_counts": inspection["distinct_counts"],
            "outcome_field": inspection["outcome_field"],
            "outcome_nonempty": inspection["outcome_nonempty"],
            "outcome_distinct_count": inspection["outcome_distinct_count"],
            "denial_reason_field_present": resolved["denial_reason"] is not None,
            "treatment_field_present": resolved["treatment"] is not None,
            "findings_field_present": resolved["findings"] is not None,
            "case_reference_field_present": resolved["case_reference"] is not None,
        },
        "privacy_scan": inspection["privacy"],
        "gates": {
            "schema_mapping": {
                "status": "human_review_required",
                "appeal_type": "nullable_unverified",
                "denial_reason": "use_only_if_explicitly_present_and_verified",
            },
            "privacy": "pending_human_review",
            "reuse": "pending_source_specific_review",
            "prior_authorization": "not_verified",
        },
        "evaluation": {
            "accepted_record_count": 0,
            "appeal_cases_evaluated": 0,
            "regulator_ground_truth_comparisons": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    input_path = args.csv.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    if input_path == output_path:
        raise ValueError("refusing to overwrite the raw CSV with its inspection report")
    report = inspect(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "data_rows": report["inspection"]["data_rows"],
                "sha256": report["artifact"]["sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
