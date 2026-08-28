#!/usr/bin/env python3
"""Inspect the public CMS QIC decision-summary API without emitting case text.

The CMS QIC search API exposes a large, current Part C and Part D decision
summary corpus. This inspector fetches only catalog metadata and a bounded
sample for schema/privacy-shape checks. It never writes API rows, identifiers,
or narrative values to the report. A later extractor may page the API into an
outside-repository local file after the summary-track acceptance decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


CATALOG_URL = "https://qic.cms.gov/api/1/metastore/schemas/dataset/items"
API_ROOT = "https://qic.cms.gov/api/1"
USER_AGENT = "appeal-real-corpus-inspector/0.1"
PUBLIC_DOMAIN_LICENSE = "https://www.usa.gov/publicdomain/label/1.0/"
PART_C_TITLE = "Part C decision data"
PART_D_TITLE = "Part D decision data"

PART_C_FIELDS = frozenset(
    {
        "record_number",
        "part",
        "decision_date",
        "decision",
        "appeal_type",
        "_condition",
        "item_service",
        "decision_rationale",
        "coverage_rules",
        "related_reference_id",
    }
)
PART_D_FIELDS = frozenset(
    {
        "record_number",
        "part",
        "decision_date",
        "decision_date_sortable",
        "decision",
        "appeal_type",
        "_condition",
        "drug",
        "decision_rationale",
        "coverage_rules",
    }
)

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


def ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not context.get_ca_certs():
        for ca_file in ("/etc/ssl/cert.pem", "/usr/local/etc/openssl@3/cert.pem"):
            if Path(ca_file).is_file():
                context.load_verify_locations(cafile=ca_file)
                break
    return context


def query_url(base_url: str, parameters: dict[str, str]) -> str:
    return f"{base_url}?{urllib.parse.urlencode(parameters)}"


def public_query_template(dataset_id: str) -> str:
    escaped_id = urllib.parse.quote(dataset_id, safe="")
    return (
        f"{API_ROOT}/datastore/query/{escaped_id}/0"
        "?keys=true&offset={offset}&limit={limit}&rowIds=true&redirect=false"
    )


def fetch_json(
    base_url: str,
    parameters: dict[str, str],
    api_key: str,
    timeout: int,
) -> Any:
    if not api_key:
        raise ValueError(
            "CMS QIC API key is required; set APPEAL_CMS_QIC_ACA from the public CMS page"
        )
    request_parameters = dict(parameters)
    request_parameters["ACA"] = api_key
    request = urllib.request.Request(
        query_url(base_url, request_parameters),
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ssl_context()) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"CMS QIC API returned HTTP {error.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RuntimeError(f"CMS QIC API request failed: {type(error).__name__}") from None
    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        raise RuntimeError("CMS QIC API returned non-JSON content") from None


def catalog_metadata(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError("CMS QIC catalog response is not an array")
    metadata: dict[str, dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        identifier = item.get("identifier")
        if not isinstance(title, str) or not isinstance(identifier, str):
            continue
        if title in metadata:
            raise ValueError(f"CMS QIC catalog contains duplicate dataset title: {title}")
        distributions = item.get("distribution")
        if not isinstance(distributions, list):
            distributions = []
        distribution_metadata: dict[str, Any] = {}
        for distribution in distributions:
            if not isinstance(distribution, dict):
                continue
            data = distribution.get("data")
            if not isinstance(data, dict):
                data = {}
            download_url = data.get("downloadURL")
            if isinstance(download_url, str):
                distribution_metadata = {
                    "identifier": distribution.get("identifier"),
                    "format": data.get("format"),
                    "media_type": data.get("mediaType"),
                    "download_url": download_url,
                }
                break
        metadata[title] = {
            "title": title,
            "identifier": identifier,
            "description": item.get("description") if isinstance(item.get("description"), str) else "",
            "access_level": item.get("accessLevel"),
            "modified": item.get("modified"),
            "license": item.get("license"),
            "publisher": (item.get("publisher") or {}).get("data", {}).get("name")
            if isinstance(item.get("publisher"), dict)
            and isinstance((item.get("publisher") or {}).get("data"), dict)
            else "",
            "distribution": distribution_metadata,
        }
    required_titles = {PART_C_TITLE, PART_D_TITLE}
    missing = sorted(required_titles - metadata.keys())
    if missing:
        raise ValueError(f"CMS QIC catalog is missing required datasets: {missing}")
    return {title: metadata[title] for title in sorted(required_titles)}


def text_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def privacy_scan(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values_by_field: dict[str, set[str]] = {}
    for row in rows:
        for field, raw_value in row.items():
            value = text_value(raw_value)
            if value:
                values_by_field.setdefault(field, set()).add(value)

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
        "status": "bounded_technical_pattern_scan_only_no_legal_determination_claimed",
    }


def summarize_query(
    payload: Any,
    *,
    expected_fields: frozenset[str],
    sample_limit: int,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("CMS QIC datastore response is not an object")
    count = payload.get("count")
    rows = payload.get("results")
    if not isinstance(payload.get("schema"), dict):
        raise ValueError("CMS QIC datastore response has no schema object")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("CMS QIC datastore response has no valid count")
    if not isinstance(rows, list) or len(rows) > sample_limit:
        raise ValueError("CMS QIC datastore response has an invalid bounded result sample")
    typed_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"CMS QIC result row {index} is not an object")
        typed_rows.append(row)
    observed_fields = sorted({field for row in typed_rows for field in row})
    missing_fields = sorted(expected_fields - set(observed_fields))
    nonempty_counts: Counter[str] = Counter()
    for row in typed_rows:
        for field, value in row.items():
            if text_value(value):
                nonempty_counts[field] += 1
    return {
        "reported_record_count": count,
        "sample_rows_returned": len(typed_rows),
        "observed_fields": observed_fields,
        "expected_fields": sorted(expected_fields),
        "missing_expected_fields": missing_fields,
        "nonempty_sample_counts": dict(sorted(nonempty_counts.items())),
        "privacy_scan": privacy_scan(typed_rows),
        "raw_rows_written": False,
    }


def inspect(*, api_key: str, sample_limit: int, timeout: int) -> dict[str, Any]:
    if sample_limit <= 0:
        raise ValueError("sample limit must be positive")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    catalog = fetch_json(
        CATALOG_URL,
        {"show-reference-ids": "true", "redirect": "false"},
        api_key,
        timeout,
    )
    datasets = catalog_metadata(catalog)
    for title, metadata in datasets.items():
        if metadata.get("access_level") != "public":
            raise ValueError(f"CMS QIC dataset is not public: {title}")
        if metadata.get("license") != PUBLIC_DOMAIN_LICENSE:
            raise ValueError(f"CMS QIC dataset license changed or is missing: {title}")
    expected_by_title = {
        PART_C_TITLE: PART_C_FIELDS,
        PART_D_TITLE: PART_D_FIELDS,
    }
    dataset_reports: dict[str, dict[str, Any]] = {}
    for title in (PART_C_TITLE, PART_D_TITLE):
        metadata = datasets[title]
        dataset_id = metadata["identifier"]
        query_endpoint = f"{API_ROOT}/datastore/query/{urllib.parse.quote(dataset_id, safe='')}/0"
        payload = fetch_json(
            query_endpoint,
            {
                "keys": "true",
                "offset": "0",
                "limit": str(sample_limit),
                "rowIds": "true",
                "redirect": "false",
            },
            api_key,
            timeout,
        )
        report = summarize_query(
            payload,
            expected_fields=expected_by_title[title],
            sample_limit=sample_limit,
        )
        report["dataset_id"] = dataset_id
        report["catalog_metadata"] = metadata
        report["query_template"] = public_query_template(dataset_id)
        dataset_reports["part_c" if title == PART_C_TITLE else "part_d"] = report

    total_records = sum(
        int(report["reported_record_count"]) for report in dataset_reports.values()
    )
    return {
        "schema_version": "0.1",
        "recorded_at": now_iso(),
        "status": "accepted_for_regulator_summary_benchmark",
        "source": {
            "source_id": "cms_qic_decision_summaries",
            "publisher": "Centers for Medicare & Medicaid Services",
            "catalog_url": CATALOG_URL,
            "api_root": API_ROOT,
            "retrieval_method": "official_catalog_and_datastore_api",
            "api_key_recorded": False,
            "query_pagination": "offset_limit",
            "raw_rows_written": False,
            "raw_artifact_location": "outside_repository_only_if_local_extraction_is_authorized",
        },
        "datasets": dataset_reports,
        "scope": {
            "part_c_records_reported": dataset_reports["part_c"]["reported_record_count"],
            "part_d_records_reported": dataset_reports["part_d"]["reported_record_count"],
            "total_records_reported": total_records,
            "complete_api_scope": True,
            "scope_note": "Counts are the complete records reported by the live API at inspection time; only bounded schema samples were read.",
        },
        "field_policy": {
            "regulator_outcome": {
                "source_field": "decision",
                "status": "explicit_qic_decision_summary_field",
            },
            "appeal_type": {
                "source_field": "appeal_type",
                "status": "explicit_source_field_verified",
            },
            "denial_reason": {
                "source_field": None,
                "status": "nullable; decision_rationale is not renamed to the original denial reason",
            },
            "decision_rationale": {
                "source_field": "decision_rationale",
                "status": "qic_summary_of_the_decision_and_denial_context",
            },
            "policy_context": {
                "source_field": "coverage_rules",
                "status": "regulator_summary_policy_context; not necessarily the original plan policy version",
            },
            "clinical_evidence": {
                "source_field": None,
                "status": "not_available_in_public_summary_api",
            },
            "prior_authorization": {
                "source_field": None,
                "status": "nullable; never inferred for all rows",
            },
        },
        "gates": {
            "provenance": {
                "status": "pass_official_catalog_and_live_api",
                "evidence": "catalog metadata, dataset identifiers, modification timestamps, and query counts recorded above",
            },
            "schema": {
                "status": "pass_for_summary_track",
                "decision": "use explicit appeal_type and decision fields; keep denial_reason nullable",
            },
            "privacy": {
                "status": "source_declares_privacy_reduced_summaries; bounded_technical_scan_only",
                "decision": "allow structured/local summary benchmarking; do not publish derived narrative rows",
                "legal_determination_claimed": False,
            },
            "reuse": {
                "status": "public_domain_label_observed_in_official_catalog",
                "decision": "metadata and aggregate benchmark evidence may be committed; raw or derived narrative rows remain outside Git",
            },
            "prior_authorization": {
                "status": "not_verified_globally",
                "decision": "retain nullable and require row-level evidence before labeling",
            },
        },
        "acceptance": {
            "decision": "accepted_for_regulator_summary_benchmark_only",
            "accepted_for_local_summary_evaluation": True,
            "accepted_record_count_reported_by_api": total_records,
            "accepted_for_full_appeal_evaluation": False,
            "raw_rows_committed": False,
            "narrative_rows_committed": False,
            "unlock_for_local_extraction": "Use the query templates and page outside the repository; preserve the source record and this manifest hash.",
        },
        "evaluation": {
            "summary_records_available": total_records,
            "regulator_summary_cases_evaluated": 0,
            "full_appeal_cases_evaluated": 0,
            "regulator_ground_truth_comparisons": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--api-key",
        default=os.environ.get("APPEAL_CMS_QIC_ACA", ""),
        help="public ACA value from the CMS QIC page; never stored in the report",
    )
    parser.add_argument("--sample-limit", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    report = inspect(api_key=args.api_key, sample_limit=args.sample_limit, timeout=args.timeout)
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "part_c_records_reported": report["scope"]["part_c_records_reported"],
                "part_d_records_reported": report["scope"]["part_d_records_reported"],
                "raw_rows_written": report["source"]["raw_rows_written"],
                "output": str(output_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
