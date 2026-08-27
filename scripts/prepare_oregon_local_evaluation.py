#!/usr/bin/env python3
"""Prepare a local-only Oregon external-review evaluation input.

The source workbook stays unchanged. The generated file must be outside this
repository and contains the treatment text needed by the local adapter plus
the regulator outcome label. No generated case input is committed to Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from inspect_oregon_iro import NS, row_values, sha256_file, shared_strings, workbook_sheets


ROOT = Path(__file__).resolve().parents[1]
ELIGIBLE_OUTCOMES = {
    "upheld denial": "upheld_denial",
    "overturned denial": "overturned_denial",
    "partial overturn": "partial_overturn",
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


def case_reference(case_number: str) -> str:
    return hashlib.sha256(case_number.encode("utf-8")).hexdigest()


def require_outside_repository(path: Path) -> None:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return
    raise ValueError(f"local evaluation output must be outside repository: {resolved}")


def read_manifest(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("acceptance manifest must be a JSON object")
    acceptance = document.get("acceptance")
    if not isinstance(acceptance, dict) or acceptance.get("accepted_for_local_evaluation") is not True:
        raise ValueError("Oregon acceptance manifest does not authorize local evaluation")
    return document


def iter_rows(path: Path) -> Iterator[tuple[int, dict[str, str]]]:
    with zipfile.ZipFile(path) as archive:
        strings = shared_strings(archive)
        sheets = workbook_sheets(archive)
        case_sheet = sheets.get("Case Detail Report")
        if case_sheet is None:
            raise ValueError("Case Detail Report sheet was not found")
        root = ET.fromstring(archive.read(case_sheet))
        rows = root.findall("x:sheetData/x:row", NS)
        header_row = 0
        headers: dict[str, str] = {}
        for row in rows:
            number = int(row.attrib["r"])
            values = row_values(row, strings)
            if "Case Outcome" in values.values() and "Case Category" in values.values():
                header_row = number
                headers = {column: value for column, value in values.items()}
                break
        if header_row == 0:
            raise ValueError("case-detail header row was not found")

        required = {
            "External Review Case Number",
            "Type of External Review Requested",
            "Case Outcome",
            "Case Category",
            "Full Procedure/ Service/ Treatment Name",
        }
        if not required.issubset(headers.values()):
            missing = sorted(required - set(headers.values()))
            raise ValueError(f"required Oregon fields are missing: {missing}")
        columns = {value: key for key, value in headers.items()}

        for row in rows:
            number = int(row.attrib["r"])
            if number <= header_row:
                continue
            values = row_values(row, strings)
            if not values:
                continue
            outcome = values.get(columns["Case Outcome"], "")
            normalized_outcome = ELIGIBLE_OUTCOMES.get(normalize(outcome))
            if normalized_outcome is None:
                continue
            case_number = values.get(columns["External Review Case Number"], "")
            if not case_number:
                raise ValueError(f"eligible row {number} has no external review case number")
            yield number, {
                "source_case_ref": case_reference(case_number),
                "review_type": values.get(columns["Type of External Review Requested"], ""),
                "case_category": values.get(columns["Case Category"], "").strip(),
                "treatment_text": values.get(columns["Full Procedure/ Service/ Treatment Name"], ""),
                "regulator_outcome": normalized_outcome,
                "regulator_outcome_label": " ".join(outcome.split()),
                "denial_reason": None,
                "appeal_type": None,
            }


def prepare(xlsx: Path, manifest_path: Path, output: Path) -> dict[str, Any]:
    require_outside_repository(output)
    manifest = read_manifest(manifest_path)
    expected_hash = manifest.get("artifact", {}).get("sha256")
    actual_hash = sha256_file(xlsx)
    if expected_hash != actual_hash:
        raise ValueError(f"Oregon workbook hash mismatch: expected {expected_hash}, got {actual_hash}")

    records: list[dict[str, Any]] = []
    for source_row, record in iter_rows(xlsx):
        record["source_row"] = source_row
        records.append(record)

    expected_count = manifest.get("scope", {}).get("accepted_local_rows")
    if expected_count != len(records):
        raise ValueError(f"eligible row count mismatch: manifest={expected_count}, observed={len(records)}")

    return {
        "schema_version": "0.1",
        "status": "local_only_ready_for_appeal_adapter",
        "generated_at": now_iso(),
        "source_id": "oregon_dfr_iro_case_detail_report",
        "source_workbook": {
            "file_name": xlsx.name,
            "sha256": actual_hash,
            "raw_artifact_location": "local_download_only_not_repo",
        },
        "acceptance_manifest": str(manifest_path.resolve()),
        "scope": {
            "decision": "all_completed_external_review_outcomes",
            "record_count": len(records),
            "prior_authorization_claimed": False,
            "narrative_retention": "local_only",
        },
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = prepare(args.xlsx.expanduser().resolve(), args.manifest.expanduser().resolve(), args.output.expanduser().resolve())
    args.output.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.expanduser().resolve().write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "record_count": report["scope"]["record_count"], "output": str(args.output.expanduser().resolve())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
