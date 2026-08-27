#!/usr/bin/env python3
"""Inspect the Oregon IRO case-detail workbook without emitting case rows.

This records workbook structure, aggregate category/outcome counts, and
identifier-shaped pattern counts. It never writes case numbers, treatment
strings, insurer values, or other row content to the report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"x": MAIN_NS, "r": REL_NS, "p": PACKAGE_REL_NS}
CELL_REF = re.compile(r"^([A-Z]+)[0-9]+$")

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
COMPLETED_REVIEW_OUTCOMES = {
    "upheld denial",
    "overturned denial",
    "partial overturn",
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(text.text or "" for text in item.findall(".//x:t", NS)) for item in root.findall("x:si", NS)]


def workbook_sheets(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        relationship.attrib["Id"]: relationship.attrib["Target"]
        for relationship in relationships.findall("p:Relationship", NS)
    }
    sheets: dict[str, str] = {}
    for sheet in workbook.findall("x:sheets/x:sheet", NS):
        name = sheet.attrib["name"]
        target = targets[sheet.attrib[f"{{{REL_NS}}}id"]]
        sheets[name] = "xl/" + target.lstrip("/")
    return sheets


def cell_value(cell: ET.Element, strings: list[str]) -> str:
    value = cell.find("x:v", NS)
    if value is None or value.text is None:
        return ""
    raw = value.text
    if cell.attrib.get("t") == "s":
        return strings[int(raw)]
    return raw


def row_values(row: ET.Element, strings: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for cell in row.findall("x:c", NS):
        reference = CELL_REF.match(cell.attrib.get("r", ""))
        if reference is None:
            continue
        value = cell_value(cell, strings)
        if value:
            values[reference.group(1)] = value
    return values


def privacy_patterns(values: set[str]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for value in values:
        if EMAIL.search(value):
            counts["email_shape"] += 1
        if PHONE.search(value):
            counts["phone_shape"] += 1
        if SSN.search(value):
            counts["ssn_shape"] += 1
        if MEMBER_ID.search(value):
            counts["member_id_label"] += 1
        if DOB.search(value):
            counts["date_of_birth_label"] += 1
        if ADDRESS.search(value):
            counts["physical_address_shape"] += 1
    return dict(sorted(counts.items()))


def inspect(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        strings = shared_strings(archive)
        sheets = workbook_sheets(archive)
        if "Case Detail Report" not in sheets:
            raise ValueError("Case Detail Report sheet was not found")
        case_root = ET.fromstring(archive.read(sheets["Case Detail Report"]))
        definitions_present = "Field Definitions" in sheets
        dimension = case_root.find("x:dimension", NS)
        rows = case_root.findall("x:sheetData/x:row", NS)
        header_row_number = 0
        headers: dict[str, str] = {}
        row_cache: dict[int, dict[str, str]] = {}
        for row in rows:
            number = int(row.attrib["r"])
            values = row_values(row, strings)
            row_cache[number] = values
            if "Case Outcome" in values.values() and "Case Category" in values.values():
                header_row_number = number
                headers = {column: value for column, value in values.items()}
                break
        if header_row_number == 0:
            raise ValueError("case-detail header row was not found")

        field_counters: dict[str, Counter[str]] = {header: Counter() for header in headers.values()}
        field_distinct: dict[str, set[str]] = {header: set() for header in headers.values()}
        all_values: set[str] = set()
        data_rows = 0
        for row in rows:
            number = int(row.attrib["r"])
            if number <= header_row_number:
                continue
            values = row_cache.get(number, row_values(row, strings))
            if not values:
                continue
            data_rows += 1
            for column, header in headers.items():
                value = values.get(column, "")
                if not value:
                    continue
                field_counters[header][value] += 1
                field_distinct[header].add(value)
                all_values.add(value)

    categorical_fields = {
        "Type of External Review Requested": "review_type_counts",
        "Case Outcome": "case_outcome_counts",
        "Case Category": "case_category_counts",
    }
    categorical_counts = {
        output_name: dict(sorted(field_counters[field].items(), key=lambda item: (-item[1], item[0])))
        for field, output_name in categorical_fields.items()
    }
    completed_review_rows = sum(
        count
        for value, count in field_counters["Case Outcome"].items()
        if " ".join(value.split()).casefold() in COMPLETED_REVIEW_OUTCOMES
    )
    return {
        "schema_version": "0.1",
        "recorded_at": now_iso(),
        "status": "public_source_acquired_local_evaluation_authorized",
        "artifact": {
            "source_id": "oregon_dfr_iro_case_detail_report",
            "publisher": "Oregon Division of Financial Regulation",
            "source_page_url": "https://dfr.oregon.gov/insure/health/understand/coverage/Pages/iro-decision-report.aspx",
            "workbook_url": "https://dfr.oregon.gov/insure/health/understand/coverage/Documents/iro-case-detail-report.xlsx",
            "file_name": path.name,
            "retrieval_method": "official_direct_download",
            "retrieval_date": datetime.now(UTC).date().isoformat(),
            "local_file_size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "raw_artifact_location": "local_download_only_not_repo",
            "transformation": "none",
        },
        "inspection": {
            "workbook_sheets": list(sheets),
            "case_detail_sheet": "Case Detail Report",
            "field_definitions_sheet_present": definitions_present,
            "dimension": dimension.attrib.get("ref", "") if dimension is not None else "",
            "header_row": header_row_number,
            "data_rows": data_rows,
            "columns": len(headers),
            "headers": [headers[column] for column in sorted(headers)],
            "distinct_counts": {field: len(values) for field, values in sorted(field_distinct.items())},
            "categorical_counts": categorical_counts,
            "narrative_or_free_text_fields_present": "Full Procedure/ Service/ Treatment Name" in headers.values(),
            "completed_review_rows_accepted_locally": completed_review_rows,
        },
        "privacy_scan": {
            "scope": "Distinct non-empty values in the Case Detail Report only; no values are emitted.",
            "distinct_values_scanned": len(all_values),
            "candidate_counts": privacy_patterns(all_values),
            "status": "technical_pattern_scan_only_no_legal_determination_claimed",
        },
        "terms": {
            "public_download_link_observed": True,
            "redacted_synopses_available_on_request": True,
            "synopsis_request_contact": "Exreview.Ins@dcbs.oregon.gov",
            "reuse_status": "operator_authorized_local_only_pending_written_confirmation_for_redistribution",
            "raw_artifact_committed": False,
            "derived_public_dataset_created": False,
            "local_evaluation_acceptance": "evidence/oregon-acceptance.json",
        },
        "evaluation_status": {
            "accepted_into_evaluation_corpus": True,
            "accepted_record_count": completed_review_rows,
            "appeal_evaluation_run": False,
            "ground_truth_comparison_run": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.xlsx.expanduser().resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "data_rows": report["inspection"]["data_rows"], "sha256": report["artifact"]["sha256"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
