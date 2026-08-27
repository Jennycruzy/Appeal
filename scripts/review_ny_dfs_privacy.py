#!/usr/bin/env python3
"""Interactively review NY DFS privacy candidates without persisting values.

The reviewer sees each candidate value only in the terminal while the
unchanged workbook is open locally. The decision file contains hashes,
locators, categories, decisions, and reviewer metadata; it never contains the
candidate value, case number, or narrative text. The output must be outside
the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from inspect_ny_export import parse_shared_strings, sheet_cells, sheet_rows


ROOT = Path(__file__).resolve().parents[1]
CELL_LOCATOR = re.compile(r"^Sheet0!([A-Z]+)([0-9]+)$")


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_value(cell_type: str, raw: str, shared_strings: dict[int, str]) -> str:
    if not raw:
        return ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except KeyError as error:
            raise RuntimeError(f"missing shared-string index {raw}") from error
    return raw


def candidate_value_map(
    xlsx: Path,
    candidates: list[dict[str, Any]],
) -> dict[str, str]:
    locator_to_hash: dict[tuple[str, int], str] = {}
    for candidate in candidates:
        value_hash = str(candidate.get("value_sha256", ""))
        locators = candidate.get("locators", [])
        if not isinstance(locators, list) or not value_hash:
            raise ValueError("each privacy candidate requires a value_sha256 and locators")
        for locator in locators:
            match = CELL_LOCATOR.fullmatch(str(locator))
            if match is None:
                raise ValueError(f"invalid privacy candidate locator: {locator}")
            locator_to_hash[(match.group(1), int(match.group(2)))] = value_hash

    with zipfile.ZipFile(xlsx) as archive:
        with archive.open("xl/sharedStrings.xml") as stream:
            header_strings, _ = parse_shared_strings(stream, set(range(19)), header_only=True)
        sheet = archive.read("xl/worksheets/sheet1.xml")
        needed: set[int] = set()
        for row_number, body_start, body_end in sheet_rows(sheet):
            for column, cell_type, raw in sheet_cells(sheet, body_start, body_end):
                if row_number > 1 and (column, row_number) in locator_to_hash and cell_type == "s" and raw:
                    needed.add(int(raw))
        with archive.open("xl/sharedStrings.xml") as stream:
            shared_strings, _ = parse_shared_strings(stream, needed)

        result: dict[str, str] = {}
        for row_number, body_start, body_end in sheet_rows(sheet):
            for column, cell_type, raw in sheet_cells(sheet, body_start, body_end):
                value_hash = locator_to_hash.get((column, row_number))
                if value_hash is None:
                    continue
                value = resolve_value(cell_type, raw, shared_strings)
                if hashlib.sha256(value.encode("utf-8")).hexdigest() != value_hash:
                    raise ValueError(f"candidate hash mismatch at Sheet0!{column}{row_number}")
                result[value_hash] = value
    missing = sorted(set(locator_to_hash.values()) - set(result))
    if missing:
        raise ValueError(f"privacy candidate locators were not found: {len(missing)}")
    return result


def ensure_external_output(output: Path) -> None:
    try:
        output.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return
    raise ValueError(f"privacy decision output must be outside repository: {output.resolve()}")


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
            "decisions": [
                {
                    "value_sha256": str(candidate["value_sha256"]),
                    "decision": decisions[str(candidate["value_sha256"])],
                    "match_types": candidate.get("match_types", []),
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
    parser.add_argument("--xlsx", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    xlsx = args.xlsx.expanduser().resolve()
    packet_path = args.packet.expanduser().resolve()
    output = args.output.expanduser().resolve()
    ensure_external_output(output)
    if not xlsx.is_file():
        raise FileNotFoundError(f"NY DFS workbook does not exist: {xlsx}")
    if not packet_path.is_file():
        raise FileNotFoundError(f"privacy packet does not exist: {packet_path}")
    if output.exists() and not args.replace:
        raise FileExistsError(f"refusing to overwrite existing decision file: {output}")

    packet = load_json(packet_path)
    packet_source = packet.get("source", {})
    expected_hash = str(packet_source.get("sha256", ""))
    actual_hash = sha256_file(xlsx)
    if actual_hash != expected_hash:
        raise ValueError(f"workbook hash mismatch: expected {expected_hash}, got {actual_hash}")
    privacy = packet.get("privacy_review", {})
    candidates = privacy.get("candidate_records", [])
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("privacy packet has no candidate records")
    candidate_values = candidate_value_map(xlsx, candidates)
    reviewer = str(args.reviewer).strip() or input("Reviewer identifier: ").strip()
    if not reviewer:
        raise ValueError("reviewer identifier is required")

    decisions: dict[str, str] = {}
    choices = {
        "f": "false_positive_public_context",
        "r": "remove_or_redact_before_use",
        "b": "confirmed_identifier_block",
        "l": "needs_legal_review",
    }
    for index, candidate in enumerate(candidates, start=1):
        value_hash = str(candidate["value_sha256"])
        print(f"\nCandidate {index}/{len(candidates)}")
        print(f"Match types: {', '.join(str(item) for item in candidate.get('match_types', []))}")
        print(f"Fields: {', '.join(str(item) for item in candidate.get('fields', []))}")
        print(f"Locators: {', '.join(str(item) for item in candidate.get('locators', []))}")
        print(f"Value (terminal only): {candidate_values[value_hash]}")
        while True:
            choice = input("Decision [f=false positive, r=redact, b=block, l=legal review, q=quit]: ").strip().lower()
            if choice == "q":
                write_decisions(
                    output,
                    source={"file_name": xlsx.name, "sha256": actual_hash},
                    reviewer=reviewer,
                    candidates=candidates,
                    decisions=decisions,
                    status="partial",
                )
                print(f"Saved partial metadata-only review: {output}")
                return 0
            if choice in choices:
                decisions[value_hash] = choices[choice]
                break
            print("Choose f, r, b, l, or q.")

    write_decisions(
        output,
        source={"file_name": xlsx.name, "sha256": actual_hash},
        reviewer=reviewer,
        candidates=candidates,
        decisions=decisions,
        status="complete",
    )
    print(f"Saved metadata-only privacy decisions: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
