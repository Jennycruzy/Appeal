#!/usr/bin/env python3
"""Scan the complete CMS QIC API scope without writing source rows.

This is the privacy gate for a full local extraction. It pages the official
API, records only aggregate candidate counts and hashed row/field locators, and
never writes a source value, record number, identifier, or narrative. A report
with candidates requires human review before the normalized extractor may be
rerun with its explicit privacy override.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from fetch_cms_qic_summary import DATASET_IDS, row_fingerprint, stable_reference
from inspect_cms_qic import API_ROOT, fetch_json, privacy_categories, text_value


USER_AGENT: Final[str] = "appeal-cms-qic-privacy-scanner/0.1"


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def value_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def scan(
    *,
    part: str,
    output: Path,
    api_key: str,
    page_size: int,
    timeout: int,
) -> dict[str, Any]:
    if part not in DATASET_IDS:
        raise ValueError(f"unknown CMS QIC part: {part}")
    if not api_key:
        raise ValueError("CMS QIC API key is required; set APPEAL_CMS_QIC_ACA")
    if page_size <= 0 or page_size > 10000:
        raise ValueError("page_size must be between 1 and 10000")
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    dataset_id = DATASET_IDS[part]
    endpoint = f"{API_ROOT}/datastore/query/{dataset_id}/0"
    source_count: int | None = None
    offset = 0
    pages = 0
    rows_scanned = 0
    candidate_counts: Counter[str] = Counter()
    candidate_counts_by_field: dict[str, Counter[str]] = {}
    candidate_locators: list[dict[str, Any]] = []

    while True:
        requested = page_size
        if source_count is not None:
            remaining = source_count - rows_scanned
            if remaining <= 0:
                break
            requested = min(requested, remaining)
        payload = fetch_json(
            endpoint,
            {
                "keys": "true",
                "offset": str(offset),
                "limit": str(requested),
                "rowIds": "true",
                "redirect": "false",
            },
            api_key,
            timeout,
        )
        if not isinstance(payload, dict):
            raise ValueError("CMS QIC privacy scan page is not an object")
        reported_count = payload.get("count")
        rows = payload.get("results")
        if not isinstance(reported_count, int) or isinstance(reported_count, bool) or reported_count < 0:
            raise ValueError("CMS QIC privacy scan page has no valid count")
        if source_count is None:
            source_count = reported_count
        elif source_count != reported_count:
            raise ValueError("CMS QIC reported count changed during privacy scan")
        if not isinstance(rows, list) or len(rows) > requested:
            raise ValueError("CMS QIC privacy scan page has invalid results")
        if not rows:
            if rows_scanned < reported_count:
                raise ValueError("CMS QIC privacy scan ended before its reported count")
            break

        pages += 1
        for page_index, raw_row in enumerate(rows):
            if not isinstance(raw_row, dict):
                raise ValueError("CMS QIC privacy scan row is not an object")
            row_offset = offset + page_index
            row_hash = row_fingerprint(raw_row)
            reference_hash = stable_reference(part, raw_row.get("record_number"))
            for field, raw_value in raw_row.items():
                value = text_value(raw_value)
                categories = privacy_categories(value) if value else ()
                if not categories:
                    continue
                field_counts = candidate_counts_by_field.setdefault(field, Counter())
                for category in categories:
                    candidate_counts[category] += 1
                    field_counts[category] += 1
                candidate_locators.append(
                    {
                        "api_offset": row_offset,
                        "field": field,
                        "categories": list(categories),
                        "source_record_ref_sha256": reference_hash,
                        "source_row_sha256": row_hash,
                        "value_sha256": value_hash(value),
                        "value_length": len(value),
                    }
                )
            rows_scanned += 1
        offset += len(rows)
        if len(rows) < requested:
            raise ValueError("CMS QIC privacy scan returned a short page before the target ended")

    if source_count is None:
        raise ValueError("CMS QIC privacy scan returned no pages")
    if rows_scanned != source_count:
        raise ValueError(f"CMS QIC privacy scan count mismatch: expected {source_count}, got {rows_scanned}")

    report = {
        "schema_version": "0.1",
        "recorded_at": now_iso(),
        "status": "privacy_candidates_require_human_review" if candidate_locators else "privacy_scan_complete_no_candidates",
        "source_id": "cms_qic_decision_summaries",
        "source": {
            "part": part,
            "dataset_id": dataset_id,
            "api_endpoint_template": f"{endpoint}?keys=true&offset={{offset}}&limit={{limit}}&rowIds=true&redirect=false",
            "api_key_recorded": False,
            "reported_source_count": source_count,
            "pages_scanned": pages,
            "rows_scanned": rows_scanned,
            "raw_rows_written": False,
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
        "acceptance": {
            "accepted_for_local_evaluation": False,
            "accepted_record_count": 0,
            "narrative_rows_committed": False,
            "full_appeal_evaluation_allowed": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".partial",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", choices=sorted(DATASET_IDS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--api-key",
        default=os.environ.get("APPEAL_CMS_QIC_ACA", ""),
        help="public ACA value from the CMS QIC page; never stored in the report",
    )
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    report = scan(
        part=args.part,
        output=args.output.expanduser().resolve(),
        api_key=args.api_key,
        page_size=args.page_size,
        timeout=args.timeout,
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "part": report["source"]["part"],
                "rows_scanned": report["source"]["rows_scanned"],
                "candidate_locator_count": report["privacy_scan"]["candidate_locator_count"],
                "output": str(args.output.expanduser().resolve()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
