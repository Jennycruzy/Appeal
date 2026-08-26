#!/usr/bin/env python3
"""Inspect an NY DFS XLSX export without emitting case narratives."""

from __future__ import annotations

import argparse
import html
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import BinaryIO, Iterator


CATEGORY_COLUMNS = set("ABCDEFGHIJK")
SUMMARY_COLUMNS = set("LMNO")
REFERENCE_COLUMNS = set("PQRS")
ROW_PATTERN = re.compile(rb'<row\b[^>]*\br="(\d+)"[^>]*>(.*?)</row>', re.S)
CELL_PATTERN = re.compile(rb'<c\b([^>]*)>(.*?)</c>|<c\b([^>]*)/>', re.S)
REFERENCE_PATTERN = re.compile(rb'\br="([A-Z]+)\d+"')
TYPE_PATTERN = re.compile(rb'\bt="([^"]+)"')
VALUE_PATTERN = re.compile(rb'<v>(.*?)</v>', re.S)


def decode_xml(raw: bytes) -> str:
    value = raw.decode("utf-8", errors="replace")
    return html.unescape(value) if "&" in value else value


def shared_string_value(body: bytes) -> str:
    parts: list[str] = []
    position = 0
    while True:
        start = body.find(b"<t", position)
        if start < 0:
            break
        content_start = body.find(b">", start)
        content_end = body.find(b"</t>", content_start + 1)
        if content_start < 0 or content_end < 0:
            raise RuntimeError("malformed shared string item")
        parts.append(decode_xml(body[content_start + 1 : content_end]))
        position = content_end + 4
    return "".join(parts)


def parse_shared_strings(
    stream: BinaryIO,
    wanted: set[int] | None = None,
    header_only: bool = False,
) -> tuple[dict[int, str], int]:
    """Parse shared strings while retaining only requested indexes."""

    data = stream.read(64 * 1024 if header_only else -1)
    values: dict[int, str] = {}
    position = 0
    index = 0
    while True:
        start = data.find(b"<si>", position)
        if start < 0:
            break
        end = data.find(b"</si>", start + 4)
        if end < 0:
            raise RuntimeError("unterminated shared string item")
        if wanted is None or index in wanted:
            values[index] = shared_string_value(data[start + 4 : end])
        index += 1
        position = end + 5
        if header_only and index >= 19:
            break
    if header_only and index < 19:
        raise RuntimeError("the workbook does not contain all header strings")
    return values, index


def sheet_rows(data: bytes) -> Iterator[tuple[int, int, int]]:
    for row in ROW_PATTERN.finditer(data):
        body_start, body_end = row.span(2)
        yield int(row.group(1)), body_start, body_end


def sheet_cells(data: bytes, body_start: int, body_end: int) -> Iterator[tuple[str, str, str]]:
    for match in CELL_PATTERN.finditer(data, body_start, body_end):
        attrs_start, attrs_end = match.span(1) if match.group(1) is not None else match.span(3)
        value_start, value_end = match.span(2)
        attrs = data[attrs_start:attrs_end]
        reference = REFERENCE_PATTERN.search(attrs)
        if reference is None:
            continue
        type_match = TYPE_PATTERN.search(attrs)
        cell_type = type_match.group(1).decode("ascii") if type_match else ""
        if cell_type == "inlineStr":
            value = shared_string_value(data[value_start:value_end])
        else:
            value_match = VALUE_PATTERN.search(data, value_start, value_end)
            if value_match is None:
                value = ""
            else:
                raw_start, raw_end = value_match.span(1)
                value = decode_xml(data[raw_start:raw_end])
        yield reference.group(1).decode("ascii"), cell_type, value


class SheetIndex:
    """First pass: collect schema, counts, and string indexes to inspect."""

    def __init__(self, header_strings: dict[int, str]) -> None:
        self.header_strings = header_strings
        self.headers: dict[str, str] = {}
        self.data_rows = 0
        self.nonempty_rows = 0
        self.max_row = 0
        self.category_id_counts: dict[str, Counter[int]] = defaultdict(Counter)
        self.category_literal_counts: dict[str, Counter[str]] = defaultdict(Counter)
        self.summary_ids_by_column: dict[str, set[int]] = defaultdict(set)
        self.summary_literals_by_column: dict[str, set[str]] = defaultdict(set)
        self.present_columns: set[str] = set()
        self.summary_row_has_content = False
        self.reference_row_has_content = False
        self.summary_rows = 0
        self.reference_rows = 0
        self.nonempty: Counter[str] = Counter()
        self.missing: Counter[str] = Counter()
        self.unique_id_counts: dict[str, set[int]] = defaultdict(set)
        self.unique_literal_counts: dict[str, set[str]] = defaultdict(set)

    def parse(self, data: bytes) -> None:
        for row_number, body_start, body_end in sheet_rows(data):
            self.max_row = max(self.max_row, row_number)
            self.present_columns = set()
            self.summary_row_has_content = False
            self.reference_row_has_content = False
            for column, cell_type, raw in sheet_cells(data, body_start, body_end):
                if not raw:
                    continue
                if row_number == 1:
                    if cell_type == "s":
                        self.headers[column] = self.header_strings[int(raw)]
                    else:
                        self.headers[column] = raw
                    continue
                self.present_columns.add(column)
                header = self.headers[column]
                self.nonempty[header] += 1
                if cell_type == "s":
                    string_id = int(raw)
                    if column in CATEGORY_COLUMNS:
                        self.category_id_counts[header][string_id] += 1
                    elif column in SUMMARY_COLUMNS:
                        self.summary_ids_by_column[column].add(string_id)
                    if header in {"Diagnosis", "Treatment", "Health Plan", "Agent", "Case Number"}:
                        self.unique_id_counts[header].add(string_id)
                else:
                    if column in CATEGORY_COLUMNS:
                        self.category_literal_counts[header][raw] += 1
                    if header in {"Diagnosis", "Treatment", "Health Plan", "Agent", "Case Number"}:
                        self.unique_literal_counts[header].add(raw)
                    if column in SUMMARY_COLUMNS:
                        self.summary_literals_by_column[column].add(raw)
                if column in SUMMARY_COLUMNS:
                    self.summary_row_has_content = True
                if column in REFERENCE_COLUMNS:
                    self.reference_row_has_content = True
            if row_number == 1:
                continue
            self.data_rows += 1
            if self.present_columns:
                self.nonempty_rows += 1
            if self.summary_row_has_content:
                self.summary_rows += 1
            if self.reference_row_has_content:
                self.reference_rows += 1
            for column, header in self.headers.items():
                if column not in self.present_columns:
                    self.missing[header] += 1


def resolve_counts(
    id_counts: Counter[int],
    literal_counts: Counter[str],
    strings: dict[int, str],
) -> Counter[str]:
    resolved: Counter[str] = Counter(literal_counts)
    for string_id, count in id_counts.items():
        try:
            resolved[strings[string_id]] += count
        except KeyError as error:
            raise RuntimeError(f"missing shared-string index {string_id}") from error
    return resolved


def resolve_distinct(
    id_values: set[int],
    literal_values: set[str],
    strings: dict[int, str],
) -> int:
    resolved = set(literal_values)
    for string_id in id_values:
        try:
            resolved.add(strings[string_id])
        except KeyError as error:
            raise RuntimeError(f"missing shared-string index {string_id}") from error
    return len(resolved)


def narrative_stats(index: SheetIndex, strings: dict[int, str]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for column in sorted(SUMMARY_COLUMNS):
        header = index.headers[column]
        lengths = [len(value) for value in index.summary_literals_by_column[column]]
        for string_id in index.summary_ids_by_column[column]:
            try:
                lengths.append(len(strings[string_id]))
            except KeyError as error:
                raise RuntimeError(f"missing summary shared-string index {string_id}") from error
        result[header] = {
            "nonempty": index.nonempty[header],
            "max_chars": max(lengths, default=0),
        }
    return result


def privacy_scan(index: SheetIndex, strings: dict[int, str]) -> dict[str, int]:
    """Classify identifier-shaped candidates without emitting narrative values."""

    email = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
    phone = re.compile(
        r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}(?!\d)"
    )
    phone_label = re.compile(r"\b(?:phone|telephone|tel|fax|cell)\b", re.I)
    ssn = re.compile(r"\d{3}-\d{2}-\d{4}")
    member_id = re.compile(r"member\s*(?:id|number|no\.?|#)", re.I)
    member_id_value = re.compile(
        r"member\s*(?:id|number|no\.?|#)\s*(?:is|was|:|-)?\s*([A-Z0-9][A-Z0-9-]{3,})",
        re.I,
    )
    date_of_birth = re.compile(r"(?:date\s+of\s+birth|\bDOB\b)", re.I)
    date_of_birth_value = re.compile(
        r"(?:date\s+of\s+birth|\bDOB\b)\s*(?:is|was|:|-)?\s*"
        r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
        r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
        r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:,|\s)\s*\d{4})",
        re.I,
    )
    address_word = re.compile(r"\baddress\b", re.I)
    street_word = re.compile(r"\bstreet\b", re.I)
    avenue_word = re.compile(r"\bavenue\b", re.I)
    road_word = re.compile(r"\broad\b", re.I)
    zip_code = re.compile(r"\bzip\s+code\b", re.I)
    physical_address = re.compile(
        r"\b\d{1,6}\s+[A-Za-z0-9][A-Za-z0-9.'-]*"
        r"(?:\s+[A-Za-z0-9][A-Za-z0-9.'-]*){0,3}\s+"
        r"(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|"
        r"lane|ln|court|ct|way|highway|hwy)\b",
        re.I,
    )
    matches: Counter[str] = Counter()
    narrative_values: set[str] = set()
    for column in SUMMARY_COLUMNS:
        narrative_values.update(index.summary_literals_by_column[column])
        for string_id in index.summary_ids_by_column[column]:
            try:
                narrative_values.add(strings[string_id])
            except KeyError as error:
                raise RuntimeError(f"missing summary shared-string index {string_id}") from error
    matches["distinct_summary_values_scanned"] = len(narrative_values)
    for value in narrative_values:
        lower_value = value.casefold()
        if "@" in value and email.search(value):
            matches["email"] += 1
        phone_match = phone.search(value)
        if phone_match is not None:
            matches["phone_shape"] += 1
            if phone_label.search(value):
                matches["phone_labeled_shape"] += 1
        if value.count("-") >= 2 and ssn.search(value):
            matches["ssn"] += 1
        if "member" in lower_value and member_id.search(value):
            matches["member_id_label"] += 1
            member_value = member_id_value.search(value)
            if member_value is not None and any(character.isdigit() for character in member_value.group(1)):
                matches["member_id_with_value_shape"] += 1
        if ("date of birth" in lower_value or "dob" in lower_value) and date_of_birth.search(value):
            matches["date_of_birth_label"] += 1
            if date_of_birth_value.search(value) is not None:
                matches["date_of_birth_with_date_shape"] += 1
        if address_word.search(value):
            matches["address_word"] += 1
        if street_word.search(value):
            matches["street_word"] += 1
        if avenue_word.search(value):
            matches["avenue_word"] += 1
        if road_word.search(value):
            matches["road_word"] += 1
        if zip_code.search(value):
            matches["zip_code_phrase"] += 1
        if physical_address.search(value) is not None:
            matches["physical_address_shape"] += 1
    return dict(sorted(matches.items()))


def inspect(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path) as archive:
        with archive.open("xl/sharedStrings.xml") as stream:
            header_strings, _ = parse_shared_strings(stream, set(range(19)), header_only=True)
        sheet = archive.read("xl/worksheets/sheet1.xml")
        index = SheetIndex(header_strings)
        index.parse(sheet)
        needed = set()
        for counts in index.category_id_counts.values():
            needed.update(counts.keys())
        for ids in index.summary_ids_by_column.values():
            needed.update(ids)
        with archive.open("xl/sharedStrings.xml") as stream:
            shared_strings, shared_count = parse_shared_strings(stream, needed)

    categorical_counts = {
        field: dict(
            sorted(
                resolve_counts(index.category_id_counts[field], index.category_literal_counts[field], shared_strings).items(),
                key=lambda item: (-item[1], item[0]),
            )
        )
        for field in (
            "Appeal Decision",
            "Denial Reason",
            "Decision Year",
            "Coverage Type",
            "Gender",
            "Age Range",
        )
    }
    distinct_counts = {
        field: resolve_distinct(
            index.unique_id_counts[field], index.unique_literal_counts[field], shared_strings
        )
        for field in ("Diagnosis", "Treatment", "Health Plan", "Agent", "Case Number")
    }
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "workbook_type": "OOXML_XLSX",
        "sheet": "Sheet0",
        "shared_string_count": shared_count,
        "rows_in_dimension": index.max_row,
        "data_rows": index.data_rows,
        "nonempty_data_rows": index.nonempty_rows,
        "columns": len(index.headers),
        "headers": [index.headers[column] for column in sorted(index.headers)],
        "appeal_type_column_present": "Appeal Type" in index.headers.values(),
        "summary_rows_with_content": index.summary_rows,
        "reference_rows_with_content": index.reference_rows,
        "categorical_counts": categorical_counts,
        "distinct_counts": distinct_counts,
        "narrative_field_stats": narrative_stats(index, shared_strings),
        "reference_field_stats": {
            index.headers[column]: {"nonempty": index.nonempty[index.headers[column]]}
            for column in sorted(REFERENCE_COLUMNS)
        },
        "missing_by_column": dict(sorted(index.missing.items())),
        "privacy_pattern_counts_in_summary_fields": privacy_scan(index, shared_strings),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.xlsx), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
