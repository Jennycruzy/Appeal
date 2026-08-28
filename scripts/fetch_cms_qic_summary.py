#!/usr/bin/env python3
"""Extract CMS QIC decision summaries into a local-only normalized JSONL file.

The extractor uses the official datastore API and writes only outside the
repository. It never prints row values. The output is normalized for the
regulator-summary adapter; it is not a full clinical Appeal case package.
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
from typing import Any

from inspect_cms_qic import (
    API_ROOT,
    fetch_json,
    privacy_scan,
    text_value,
)


ROOT = Path(__file__).resolve().parents[1]
DATASET_IDS = {
    "part_c": "e1fc1663-7675-4d83-a8dd-5f709f440bbb",
    "part_d": "8152455d-179d-4455-9d09-e5dfc516be10",
}
SOURCE_ID = "cms_qic_decision_summaries"


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_outside_repository(path: Path, label: str) -> None:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return
    raise ValueError(f"{label} must be outside the repository: {resolved}")


def stable_reference(part: str, record_number: Any) -> str:
    value = text_value(record_number)
    if not value:
        raise ValueError("CMS QIC row has no record_number")
    return hashlib.sha256(f"{SOURCE_ID}:{part}:{value}".encode("utf-8")).hexdigest()


def row_fingerprint(row: dict[str, Any]) -> str:
    canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_row(part: str, row: dict[str, Any]) -> dict[str, Any]:
    if part not in DATASET_IDS:
        raise ValueError(f"unknown CMS QIC part: {part}")
    required = {
        "record_number",
        "part",
        "decision_date",
        "decision",
        "appeal_type",
        "_condition",
        "decision_rationale",
        "coverage_rules",
    }
    if part == "part_c":
        required.add("item_service")
        requested = row.get("item_service")
    else:
        required.add("drug")
        requested = row.get("drug")
    missing = sorted(field for field in required if field not in row)
    if missing:
        raise ValueError(f"CMS QIC {part} row is missing expected fields: {missing}")
    reference = stable_reference(part, row.get("record_number"))
    return {
        "case_id": reference,
        "source_id": SOURCE_ID,
        "source_dataset": part,
        "source_dataset_id": DATASET_IDS[part],
        "source_record_ref_sha256": reference,
        "source_row_sha256": row_fingerprint(row),
        "part": text_value(row.get("part")),
        "regulator_decision_date": text_value(row.get("decision_date")),
        "regulator_outcome": text_value(row.get("decision")),
        "appeal_type": text_value(row.get("appeal_type")) or None,
        "condition": text_value(row.get("_condition")) or None,
        "requested_item_or_drug": text_value(requested) or None,
        "decision_rationale": text_value(row.get("decision_rationale")) or None,
        "policy_context": text_value(row.get("coverage_rules")) or None,
        "denial_reason": None,
        "clinical_evidence": None,
        "prior_authorization": None,
    }


def add_privacy_counts(total: Counter[str], report: dict[str, Any]) -> None:
    counts = report.get("candidate_counts")
    if not isinstance(counts, dict):
        return
    for key, value in counts.items():
        if isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool):
            total[key] += value


def extract(
    *,
    part: str,
    output: Path,
    manifest_path: Path,
    api_key: str,
    page_size: int,
    max_records: int | None,
    timeout: int,
    fail_on_privacy_match: bool = True,
) -> dict[str, Any]:
    require_outside_repository(output, "CMS QIC extraction output")
    require_outside_repository(manifest_path, "CMS QIC extraction manifest")
    if output == manifest_path:
        raise ValueError("CMS QIC extraction output and manifest must be different files")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing extraction: {output}")
    if manifest_path.exists():
        raise FileExistsError(f"refusing to overwrite existing extraction manifest: {manifest_path}")
    if page_size <= 0 or page_size > 10000:
        raise ValueError("page_size must be between 1 and 10000")
    if max_records is not None and max_records <= 0:
        raise ValueError("max_records must be positive")
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    dataset_id = DATASET_IDS.get(part)
    if dataset_id is None:
        raise ValueError(f"unknown CMS QIC part: {part}")
    endpoint = f"{API_ROOT}/datastore/query/{dataset_id}/0"
    temporary_path: Path | None = None
    rows_written = 0
    source_count: int | None = None
    privacy_counts: Counter[str] = Counter()
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".partial",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            offset = 0
            while True:
                requested = page_size
                if max_records is not None:
                    requested = min(requested, max_records - rows_written)
                    if requested <= 0:
                        break
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
                    raise ValueError("CMS QIC datastore page is not an object")
                reported_count = payload.get("count")
                page_rows = payload.get("results")
                if not isinstance(reported_count, int) or isinstance(reported_count, bool) or reported_count < 0:
                    raise ValueError("CMS QIC datastore page has no valid count")
                if source_count is None:
                    source_count = reported_count
                elif source_count != reported_count:
                    raise ValueError("CMS QIC reported count changed during extraction")
                target_count = source_count if max_records is None else min(source_count, max_records)
                if not isinstance(page_rows, list):
                    raise ValueError("CMS QIC datastore page results are not an array")
                if len(page_rows) > requested:
                    raise ValueError("CMS QIC API returned more rows than requested")
                if not page_rows:
                    if rows_written < target_count:
                        raise ValueError("CMS QIC API ended before its reported count")
                    break

                for raw_row in page_rows:
                    if not isinstance(raw_row, dict):
                        raise ValueError("CMS QIC result row is not an object")
                    privacy = privacy_scan([raw_row])
                    add_privacy_counts(privacy_counts, privacy)
                    if fail_on_privacy_match and privacy_counts:
                        raise ValueError(
                            "privacy-shaped value detected; extraction stopped before acceptance"
                        )
                    normalized = normalize_row(part, raw_row)
                    temporary.write(json.dumps(normalized, ensure_ascii=False, sort_keys=True) + "\n")
                    rows_written += 1

                offset += len(page_rows)
                if rows_written >= target_count:
                    break
                if len(page_rows) < requested:
                    raise ValueError("CMS QIC API returned a short page before the target scope ended")
            temporary.flush()
            os.fsync(temporary.fileno())

        if source_count is None:
            raise ValueError("CMS QIC returned no pages")
        if max_records is None and rows_written != source_count:
            raise ValueError(f"extraction count mismatch: expected {source_count}, got {rows_written}")
        temporary_path.replace(output)
        temporary_path = None
        output_hash = sha256_file(output)
        manifest = {
            "schema_version": "0.1",
            "recorded_at": now_iso(),
            "status": "local_only_extraction_complete",
            "source_id": SOURCE_ID,
            "source": {
                "part": part,
                "dataset_id": dataset_id,
                "api_endpoint_template": f"{endpoint}?keys=true&offset={{offset}}&limit={{limit}}&rowIds=true&redirect=false",
                "api_key_recorded": False,
                "reported_source_count": source_count,
                "extraction_scope": "all_records" if max_records is None else f"first_{max_records}_records",
            },
            "artifact": {
                "file_name": output.name,
                "sha256": output_hash,
                "bytes": output.stat().st_size,
                "raw_artifact_location": "outside_repository_only",
                "transformation": "normalized_jsonl_with_source_row_and_reference_hashes",
                "narrative_fields_local_only": True,
            },
            "privacy_scan": {
                "candidate_counts": dict(sorted(privacy_counts.items())),
                "status": "technical_pattern_scan_only_no_legal_determination_claimed",
                "fail_on_privacy_match": fail_on_privacy_match,
            },
            "field_policy": {
                "regulator_outcome": "source decision",
                "appeal_type": "source appeal_type; explicit field",
                "denial_reason": None,
                "decision_rationale": "source QIC summary; not original denial reason",
                "policy_context": "source coverage_rules summary; not original plan policy version",
                "clinical_evidence": None,
                "prior_authorization": None,
            },
            "evaluation": {
                "records_written": rows_written,
                "summary_cases_evaluated": 0,
                "full_appeal_cases_evaluated": 0,
                "regulator_ground_truth_comparisons": 0,
            },
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return manifest
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", choices=sorted(DATASET_IDS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all", action="store_true", help="extract the complete current API result set")
    scope.add_argument("--max-records", type=int, help="extract only the first N rows for a bounded local test")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("APPEAL_CMS_QIC_ACA", ""),
        help="public ACA value from the CMS QIC page; never stored in the manifest",
    )
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument(
        "--allow-privacy-shaped-values",
        action="store_true",
        help="continue after technical pattern matches; requires separate human review",
    )
    args = parser.parse_args()
    manifest = extract(
        part=args.part,
        output=args.output.expanduser().resolve(),
        manifest_path=args.manifest.expanduser().resolve(),
        api_key=args.api_key,
        page_size=args.page_size,
        max_records=None if args.all else args.max_records,
        timeout=args.timeout,
        fail_on_privacy_match=not args.allow_privacy_shaped_values,
    )
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "part": manifest["source"]["part"],
                "records_written": manifest["evaluation"]["records_written"],
                "output": str(args.output.expanduser().resolve()),
                "manifest": str(args.manifest.expanduser().resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
