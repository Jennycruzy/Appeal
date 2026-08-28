#!/usr/bin/env python3
"""Record explicit acceptance of a conservative CMS QIC bulk subset.

The source CSV remains outside the repository. This command validates the
inspection report and the outside-repository privacy proposal, excludes every
candidate whose proposal is not ``f``, and writes a metadata-only acceptance
manifest. It does not copy source rows or narrative values.
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
from inspect_cms_qic_bulk import row_fingerprint, sha256_file
from review_cms_qic_bulk_privacy import candidate_groups, load_json, require_external


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_DECISIONS = {"f", "r", "b", "l"}


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def require_repository_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        raise ValueError(f"CMS QIC bulk acceptance manifest must be in the repository: {resolved}") from None
    return resolved


def content_identity(file_sha256: str, row_sha256: str) -> str:
    return hashlib.sha256(f"{file_sha256}:{row_sha256}".encode("utf-8")).hexdigest()


def occurrence_identity(content_sha256: str, csv_data_row: int) -> str:
    return hashlib.sha256(f"{content_sha256}:{csv_data_row}".encode("utf-8")).hexdigest()


def selection_fingerprint(items: list[str]) -> str:
    digest = hashlib.sha256()
    for item in items:
        digest.update(item.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def proposal_decisions(proposal: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    privacy = proposal.get("privacy_review")
    source = proposal.get("source")
    if not isinstance(privacy, dict) or not isinstance(source, dict):
        raise ValueError("CMS QIC privacy proposal is missing privacy_review or source metadata")
    records = privacy.get("decisions")
    if not isinstance(records, list):
        raise ValueError("CMS QIC privacy proposal has no decisions list")
    decisions: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("CMS QIC privacy proposal decision is not an object")
        value_hash = record.get("value_sha256")
        decision = record.get("decision")
        if not isinstance(value_hash, str) or len(value_hash) != 64:
            raise ValueError("CMS QIC privacy proposal has an invalid value hash")
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(f"CMS QIC privacy proposal has unsupported decision: {decision}")
        if value_hash in decisions:
            raise ValueError("CMS QIC privacy proposal repeats a value hash")
        decisions[value_hash] = decision

    expected_count = privacy.get("candidate_record_count")
    decision_count = privacy.get("decision_count")
    unresolved_count = privacy.get("unresolved_count")
    if expected_count != len(decisions) or decision_count != len(decisions) or unresolved_count != 0:
        raise ValueError("CMS QIC privacy proposal is incomplete")
    if privacy.get("raw_values_in_decision_file") is not False:
        raise ValueError("CMS QIC privacy proposal must be metadata-only")
    return decisions, source


def build_manifest(
    csv_path: Path,
    report_path: Path,
    proposal_path: Path,
    *,
    reviewer: str,
) -> dict[str, Any]:
    report = load_json(report_path)
    artifact = report.get("artifact")
    source = report.get("source")
    inspection = report.get("inspection")
    if not isinstance(artifact, dict) or not isinstance(source, dict) or not isinstance(inspection, dict):
        raise ValueError("CMS QIC bulk report is missing artifact, source, or inspection metadata")

    actual_file_sha256 = sha256_file(csv_path)
    if actual_file_sha256 != artifact.get("sha256"):
        raise ValueError("CMS QIC bulk CSV hash does not match the inspection report")
    proposal = load_json(proposal_path)
    decisions, proposal_source = proposal_decisions(proposal)
    if proposal_source.get("sha256") != actual_file_sha256:
        raise ValueError("CMS QIC privacy proposal does not match the inspected CSV")
    if proposal_source.get("source_id") != report.get("source_id"):
        raise ValueError("CMS QIC privacy proposal source ID does not match the inspection report")

    candidates = candidate_groups(report)
    candidate_hashes = {str(candidate["value_sha256"]) for candidate in candidates}
    if candidate_hashes != set(decisions):
        raise ValueError("CMS QIC privacy proposal does not cover exactly the inspection candidates")

    excluded_rows: dict[int, dict[str, Any]] = {}
    decision_group_counts: Counter[str] = Counter()
    excluded_locator_counts: Counter[str] = Counter()
    for candidate in candidates:
        decision = decisions[str(candidate["value_sha256"])]
        decision_group_counts[decision] += 1
        if decision == "f":
            continue
        for locator in candidate["locators"]:
            row_number = int(locator["csv_data_row"])
            row_hash = locator.get("source_row_sha256")
            if not isinstance(row_hash, str) or len(row_hash) != 64:
                raise ValueError("CMS QIC privacy locator is missing a valid source row hash")
            row = excluded_rows.setdefault(
                row_number,
                {
                    "csv_data_row": row_number,
                    "row_sha256": row_hash,
                    "decision_groups": [],
                    "value_hashes": [],
                },
            )
            if row["row_sha256"] != row_hash:
                raise ValueError(f"conflicting source row hashes at CSV row {row_number}")
            row["decision_groups"].append(decision)
            row["value_hashes"].append(str(candidate["value_sha256"]))
            excluded_locator_counts[decision] += 1

    expected_excluded_rows = len(excluded_rows)
    row_hash_counts: Counter[str] = Counter()
    accepted_row_hashes: set[str] = set()
    excluded_row_hashes: set[str] = set()
    accepted_occurrence_identities: list[str] = []
    excluded_occurrence_identities: list[str] = []
    total_rows = 0
    well_formed_rows = 0
    malformed_rows = 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        try:
            headers = next(reader)
        except StopIteration:
            raise ValueError("CMS QIC bulk CSV is empty") from None
        for row_number, values in enumerate(reader, start=1):
            total_rows += 1
            if len(values) != len(headers):
                malformed_rows += 1
                continue
            well_formed_rows += 1
            row_hash = row_fingerprint(dict(zip(headers, values, strict=True)))
            row_hash_counts[row_hash] += 1
            content_hash = content_identity(actual_file_sha256, row_hash)
            occurrence_hash = occurrence_identity(content_hash, row_number)
            if row_number in excluded_rows:
                excluded_row_hashes.add(row_hash)
                excluded_occurrence_identities.append(occurrence_hash)
            else:
                accepted_row_hashes.add(row_hash)
                accepted_occurrence_identities.append(occurrence_hash)

    if malformed_rows:
        raise ValueError("CMS QIC bulk CSV has malformed rows")
    if total_rows != inspection.get("rows_scanned") or well_formed_rows != inspection.get("well_formed_rows"):
        raise ValueError("CMS QIC bulk CSV row counts do not match the inspection report")
    if expected_excluded_rows != sum(1 for _ in excluded_occurrence_identities):
        raise ValueError("CMS QIC excluded row selection could not be reproduced")
    if len(excluded_row_hashes) != expected_excluded_rows:
        raise ValueError("CMS QIC excluded rows contain duplicate content hashes")

    excluded_row_counts: Counter[str] = Counter()
    for row in excluded_rows.values():
        for decision in set(row["decision_groups"]):
            excluded_row_counts[decision] += 1

    duplicate_groups = sum(1 for count in row_hash_counts.values() if count > 1)
    duplicate_extra_rows = sum(count - 1 for count in row_hash_counts.values() if count > 1)
    proposal_sha256 = sha256_file(proposal_path)
    accepted_count = total_rows - expected_excluded_rows
    return {
        "schema_version": "0.2",
        "recorded_at": now_iso(),
        "status": "accepted_for_local_summary_evaluation_with_conservative_exclusions",
        "source_id": report.get("source_id"),
        "source": {
            "part": source.get("part"),
            "dataset_id": source.get("dataset_id"),
            "source_url": source.get("source_url"),
            "etag": source.get("etag"),
            "file_name": csv_path.name,
            "bytes": artifact.get("bytes"),
            "sha256": actual_file_sha256,
            "raw_artifact_location": "outside_repository_only",
            "raw_rows_committed": False,
            "inspection_report": report_path.name,
        },
        "identity": {
            "status": "pass_for_pinned_file_local_scope",
            "stable_identity": "sha256(file_sha256 + ':' + row_sha256); occurrence order only disambiguates duplicate content rows in this pinned file",
            "file_sha256": actual_file_sha256,
            "row_sha256": "SHA-256 of canonical UTF-8 JSON for the complete CSV row with sorted source headers",
            "content_identity_sha256": "SHA-256(file_sha256 + ':' + row_sha256)",
            "source_record_number": "missing_in_bulk_export_not_resolved_or_invented",
            "row_hash_unique_count": len(row_hash_counts),
            "row_hash_duplicate_groups": duplicate_groups,
            "row_hash_duplicate_extra_rows": duplicate_extra_rows,
            "accepted_unique_content_identities": len(accepted_row_hashes),
            "excluded_unique_content_identities": len(excluded_row_hashes),
        },
        "privacy_review": {
            "status": "pass_by_explicit_user_conservative_exclusion_policy",
            "reviewer": reviewer,
            "decision_source": "explicit_user_direction_in_workspace",
            "individual_candidate_review": False,
            "policy": "include every candidate classified f; exclude every candidate classified b or l",
            "candidate_group_count": len(candidates),
            "approved_false_positive_group_count": decision_group_counts["f"],
            "excluded_non_false_positive_group_count": sum(
                count for decision, count in decision_group_counts.items() if decision != "f"
            ),
            "excluded_locator_count": sum(excluded_locator_counts.values()),
            "decision_counts": dict(sorted(decision_group_counts.items())),
            "decision_record": {
                "file_name": proposal_path.name,
                "sha256": proposal_sha256,
                "raw_values_in_decision_file": False,
            },
        },
        "selection": {
            "total_source_rows": total_rows,
            "accepted_row_count": accepted_count,
            "excluded_row_count": expected_excluded_rows,
            "excluded_rows_by_decision": dict(sorted(excluded_row_counts.items())),
            "excluded_rows": [
                {
                    "csv_data_row": row["csv_data_row"],
                    "row_sha256": row["row_sha256"],
                    "content_identity_sha256": content_identity(actual_file_sha256, row["row_sha256"]),
                    "occurrence_identity_sha256": occurrence_identity(
                        content_identity(actual_file_sha256, row["row_sha256"]), row["csv_data_row"]
                    ),
                    "decision_groups": sorted(row["decision_groups"]),
                    "value_hashes": sorted(row["value_hashes"]),
                }
                for row in sorted(excluded_rows.values(), key=lambda item: int(item["csv_data_row"]))
            ],
            "accepted_occurrence_selection_fingerprint_sha256": selection_fingerprint(
                accepted_occurrence_identities
            ),
            "excluded_occurrence_selection_fingerprint_sha256": selection_fingerprint(
                excluded_occurrence_identities
            ),
        },
        "gates": {
            "source_integrity": "pass",
            "privacy": "pass_with_explicit_conservative_exclusions",
            "stable_identity": "pass_for_pinned_file_local_scope",
            "schema": "accepted_for_local_summary_scope_with_missing_source_record_number_documented",
            "reuse": "pass_for_local_summary_benchmark_only_under_official_public_source_metadata",
            "prior_authorization": "not_verified_not_required_for_regulator_summary_track",
        },
        "acceptance": {
            "decision": "accepted_for_local_regulator_summary_evaluation_only",
            "accepted_for_local_evaluation": True,
            "accepted_for_repository": False,
            "accepted_record_count": accepted_count,
            "excluded_record_count": expected_excluded_rows,
            "raw_artifacts_committed": False,
            "narrative_rows_committed": False,
            "full_appeal_evaluation_allowed": False,
            "scope_limit": "pinned official Part D bulk artifact after explicit non-f exclusion; not a full Appeal case corpus",
        },
        "evaluation": {
            "summary_cases_evaluated": 0,
            "full_appeal_cases_evaluated": 0,
            "regulator_ground_truth_comparisons": 0,
        },
    }


def write_manifest(manifest: dict[str, Any], output: Path, *, replace: bool) -> None:
    if output.exists() and not replace:
        raise FileExistsError(f"refusing to overwrite CMS QIC bulk acceptance manifest: {output}")
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
            handle.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviewer", default="workspace-owner-explicit-direction")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    csv_path = require_external(args.csv, "CMS QIC bulk CSV")
    proposal_path = require_external(args.proposal, "CMS QIC privacy proposal")
    report_path = args.report.expanduser().resolve()
    output = require_repository_output(args.output)
    if not csv_path.is_file():
        raise FileNotFoundError(f"CMS QIC bulk CSV does not exist: {csv_path}")
    if not proposal_path.is_file():
        raise FileNotFoundError(f"CMS QIC privacy proposal does not exist: {proposal_path}")
    if not report_path.is_file():
        raise FileNotFoundError(f"CMS QIC bulk report does not exist: {report_path}")

    manifest = build_manifest(
        csv_path,
        report_path,
        proposal_path,
        reviewer=args.reviewer.strip() or "workspace-owner-explicit-direction",
    )
    write_manifest(manifest, output, replace=args.replace)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "accepted_record_count": manifest["acceptance"]["accepted_record_count"],
                "excluded_record_count": manifest["acceptance"]["excluded_record_count"],
                "output": str(output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
