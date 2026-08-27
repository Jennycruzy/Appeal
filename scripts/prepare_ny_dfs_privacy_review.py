#!/usr/bin/env python3
"""Create a local-only, hash-and-locator inventory for NY DFS privacy review.

The output intentionally contains no narrative values, case numbers, or
identifier values. It records only cell locators, value hashes, lengths, and
match categories so a reviewer can inspect the unchanged workbook locally.
The command refuses to write inside the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from inspect_ny_export import (
    SUMMARY_COLUMNS,
    parse_shared_strings,
    sheet_cells,
    sheet_rows,
)


ROOT = Path(__file__).resolve().parents[1]
ACQUISITION_PATH = ROOT / "evidence" / "ny-dfs-export-acquisition.json"

EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(
    r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}(?!\d)"
)
PHONE_LABEL = re.compile(r"\b(?:phone|telephone|tel|fax|cell)\b", re.I)
SSN = re.compile(r"\d{3}-\d{2}-\d{4}")
MEMBER_ID = re.compile(r"member\s*(?:id|number|no\.?|#)", re.I)
MEMBER_ID_VALUE = re.compile(
    r"member\s*(?:id|number|no\.?|#)\s*(?:is|was|:|-)?\s*"
    r"([A-Z0-9][A-Z0-9-]{3,})",
    re.I,
)
DATE_OF_BIRTH = re.compile(r"(?:date\s+of\s+birth|\bDOB\b)", re.I)
DATE_OF_BIRTH_VALUE = re.compile(
    r"(?:date\s+of\s+birth|\bDOB\b)\s*(?:is|was|:|-)?\s*"
    r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:,|\s)\s*\d{4})",
    re.I,
)
ADDRESS_WORD = re.compile(r"\baddress\b", re.I)
STREET_WORD = re.compile(r"\bstreet\b", re.I)
AVENUE_WORD = re.compile(r"\bavenue\b", re.I)
ROAD_WORD = re.compile(r"\broad\b", re.I)
ZIP_CODE = re.compile(r"\bzip\s+code\b", re.I)
PHYSICAL_ADDRESS = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9][A-Za-z0-9.'-]*"
    r"(?:\s+[A-Za-z0-9][A-Za-z0-9.'-]*){0,3}\s+"
    r"(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|"
    r"lane|ln|court|ct|way|highway|hwy)\b",
    re.I,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def classify(value: str) -> set[str]:
    categories: set[str] = set()
    if "@" in value and EMAIL.search(value):
        categories.add("email_shape")
    phone_match = PHONE.search(value)
    if phone_match is not None:
        categories.add("phone_shape")
        if PHONE_LABEL.search(value):
            categories.add("phone_labeled_shape")
    if value.count("-") >= 2 and SSN.search(value):
        categories.add("ssn_shape")
    lower_value = value.casefold()
    if "member" in lower_value and MEMBER_ID.search(value):
        categories.add("member_id_label")
        member_value = MEMBER_ID_VALUE.search(value)
        if member_value is not None and any(character.isdigit() for character in member_value.group(1)):
            categories.add("member_id_with_value_shape")
    if "date of birth" in lower_value or "dob" in lower_value:
        if DATE_OF_BIRTH.search(value):
            categories.add("date_of_birth_label")
            if DATE_OF_BIRTH_VALUE.search(value) is not None:
                categories.add("date_of_birth_with_date_shape")
    if ADDRESS_WORD.search(value):
        categories.add("address_word")
    if STREET_WORD.search(value):
        categories.add("street_word")
    if AVENUE_WORD.search(value):
        categories.add("avenue_word")
    if ROAD_WORD.search(value):
        categories.add("road_word")
    if ZIP_CODE.search(value):
        categories.add("zip_code_phrase")
    if PHYSICAL_ADDRESS.search(value) is not None:
        categories.add("physical_address_shape")
    return categories


def resolve_value(cell_type: str, raw: str, shared_strings: dict[int, str]) -> str:
    if not raw:
        return ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except KeyError as error:
            raise RuntimeError(f"missing shared-string index {raw}") from error
    return raw


def scan_workbook(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with zipfile.ZipFile(path) as archive:
        with archive.open("xl/sharedStrings.xml") as stream:
            header_strings, _ = parse_shared_strings(stream, set(range(19)), header_only=True)
        sheet = archive.read("xl/worksheets/sheet1.xml")

        headers: dict[str, str] = {}
        needed: set[int] = set()
        for row_number, body_start, body_end in sheet_rows(sheet):
            for column, cell_type, raw in sheet_cells(sheet, body_start, body_end):
                if row_number == 1:
                    headers[column] = header_strings[int(raw)] if cell_type == "s" else raw
                elif column in SUMMARY_COLUMNS and cell_type == "s" and raw:
                    needed.add(int(raw))

        with archive.open("xl/sharedStrings.xml") as stream:
            shared_strings, shared_count = parse_shared_strings(stream, needed)

        candidates: dict[str, dict[str, Any]] = {}
        data_rows = 0
        distinct_summary_values: set[str] = set()
        for row_number, body_start, body_end in sheet_rows(sheet):
            if row_number == 1:
                continue
            data_rows += 1
            for column, cell_type, raw in sheet_cells(sheet, body_start, body_end):
                if column not in SUMMARY_COLUMNS:
                    continue
                value = resolve_value(cell_type, raw, shared_strings)
                if not value:
                    continue
                distinct_summary_values.add(value)
                categories = classify(value)
                if not categories:
                    continue
                value_hash = hashlib.sha256(value.encode("utf-8")).hexdigest()
                candidate = candidates.setdefault(
                    value_hash,
                    {
                        "value_sha256": value_hash,
                        "value_length": len(value),
                        "fields": set(),
                        "match_types": set(),
                        "occurrence_count": 0,
                        "locators": [],
                    },
                )
                candidate["fields"].add(headers[column])
                candidate["match_types"].update(categories)
                candidate["occurrence_count"] += 1
                if len(candidate["locators"]) < 8:
                    candidate["locators"].append(f"Sheet0!{column}{row_number}")

    candidate_counts: Counter[str] = Counter()
    clean_candidates: list[dict[str, Any]] = []
    for candidate in candidates.values():
        match_types = sorted(candidate["match_types"])
        candidate_counts.update(match_types)
        clean_candidates.append(
            {
                "value_sha256": candidate["value_sha256"],
                "value_length": candidate["value_length"],
                "fields": sorted(candidate["fields"]),
                "match_types": match_types,
                "occurrence_count": candidate["occurrence_count"],
                "locators": candidate["locators"],
            }
        )
    clean_candidates.sort(key=lambda item: str(item["value_sha256"]))
    candidate_counts["distinct_summary_values_scanned"] = len(distinct_summary_values)
    return {
        "data_rows": data_rows,
        "shared_string_count": shared_count,
        "distinct_summary_values_scanned": len(distinct_summary_values),
        "candidate_counts": dict(sorted(candidate_counts.items())),
    }, clean_candidates


def ensure_external_output(output: Path) -> None:
    resolved = output.resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return
    raise ValueError(f"privacy review output must be outside repository: {resolved}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    xlsx = args.xlsx.expanduser().resolve()
    output = args.output.expanduser().resolve()
    ensure_external_output(output)
    if not xlsx.is_file():
        raise FileNotFoundError(f"NY DFS workbook does not exist: {xlsx}")
    if output.exists() and not args.replace:
        raise FileExistsError(f"refusing to overwrite existing review packet: {output}")

    acquisition = load_json(ACQUISITION_PATH)
    artifact = acquisition.get("artifact", {})
    expected_hash = str(artifact.get("sha256", ""))
    actual_hash = sha256_file(xlsx)
    if actual_hash != expected_hash:
        raise ValueError(f"workbook hash mismatch: expected {expected_hash}, got {actual_hash}")

    scan, candidates = scan_workbook(xlsx)
    report = {
        "schema_version": "0.1",
        "status": "blocked_pending_human_review",
        "source": {
            "source_id": "ny_dfs_external_appeal_archive",
            "file_name": xlsx.name,
            "sha256": actual_hash,
            "data_rows": scan["data_rows"],
        },
        "privacy_review": {
            "content_policy": "No raw narrative values, case numbers, or identifier values are written.",
            "review_instruction": "Open the unchanged workbook and inspect each locator; record only a decision and reviewer metadata in the acceptance manifest.",
            "decision_options": [
                "false_positive_public_context",
                "remove_or_redact_before_use",
                "confirmed_identifier_block",
                "needs_legal_review",
            ],
            "distinct_summary_values_scanned": scan["distinct_summary_values_scanned"],
            "candidate_counts": scan["candidate_counts"],
            "candidate_records": candidates,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(output, 0o600)
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(output),
                "sha256": actual_hash,
                "data_rows": scan["data_rows"],
                "candidate_counts": scan["candidate_counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
