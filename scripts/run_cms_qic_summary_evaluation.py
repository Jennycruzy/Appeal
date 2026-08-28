#!/usr/bin/env python3
"""Run the fail-closed CMS QIC summary adapter preflight.

The CMS QIC extractor supplies real regulator decision summaries, including an
explicit outcome and appeal type, but not the original plan denial, complete
clinical evidence, or original plan-policy version. This command validates an
outside-repository normalized extraction, inventories only aggregate labels,
exercises the case state machine, and records an explicit abstention for every
row before full Appeal evaluation.

It never writes source row values, identifiers, or narrative text to the
aggregate report. The input and its manifest must remain outside the
repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from appeal_core import (
    Actor,
    ActorKind,
    CaseState,
    CaseStateMachine,
    DecisionSource,
    DeadlineCatalog,
    EvidenceRef,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID: Final[str] = "cms_qic_decision_summaries"
DATASETS: Final[frozenset[str]] = frozenset({"part_c", "part_d"})
HASH_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
SUMMARY_FIELDS: Final[tuple[str, ...]] = (
    "appeal_type",
    "condition",
    "requested_item_or_drug",
    "decision_rationale",
    "policy_context",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_outside_repository(path: Path, label: str) -> None:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return
    raise ValueError(f"{label} must be outside repository: {resolved}")


def require_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def validate_manifest(manifest: dict[str, Any]) -> tuple[str, int]:
    if manifest.get("source_id") != SOURCE_ID:
        raise ValueError("CMS summary manifest has the wrong source_id")
    if manifest.get("status") != "local_only_extraction_complete":
        raise ValueError("CMS summary extraction is not marked complete")

    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict):
        raise ValueError("CMS summary manifest artifact is missing")
    if artifact.get("raw_artifact_location") != "outside_repository_only":
        raise ValueError("CMS summary artifact must remain outside the repository")
    expected_hash = require_hash(artifact.get("sha256"), "artifact.sha256")
    if artifact.get("narrative_fields_local_only") is not True:
        raise ValueError("CMS summary manifest must mark narrative fields local-only")

    source = manifest.get("source")
    if not isinstance(source, dict) or source.get("part") not in DATASETS:
        raise ValueError("CMS summary manifest has no valid source part")

    privacy = manifest.get("privacy_scan")
    if not isinstance(privacy, dict) or privacy.get("candidate_counts") != {}:
        raise ValueError("CMS summary extraction has unresolved privacy-shaped values")

    evaluation = manifest.get("evaluation")
    if not isinstance(evaluation, dict):
        raise ValueError("CMS summary manifest evaluation is missing")
    records_written = evaluation.get("records_written")
    if not isinstance(records_written, int) or isinstance(records_written, bool) or records_written <= 0:
        raise ValueError("CMS summary manifest records_written must be positive")
    if evaluation.get("full_appeal_cases_evaluated") != 0:
        raise ValueError("CMS summary extraction cannot claim full Appeal evaluations")
    return expected_hash, records_written


def validate_record(record: dict[str, Any], index: int, part: str) -> None:
    if set(record).intersection({"record_number", "raw_row", "source_row"}):
        raise ValueError(f"records[{index}] contains a source identifier or raw row")
    if require_hash(record.get("case_id"), f"records[{index}].case_id") != record.get("case_id"):
        raise ValueError(f"records[{index}].case_id is invalid")
    if require_hash(record.get("source_record_ref_sha256"), f"records[{index}].source_record_ref_sha256") != record.get("source_record_ref_sha256"):
        raise ValueError(f"records[{index}].source_record_ref_sha256 is invalid")
    require_hash(record.get("source_row_sha256"), f"records[{index}].source_row_sha256")
    if record.get("source_id") != SOURCE_ID:
        raise ValueError(f"records[{index}] has the wrong source_id")
    if record.get("source_dataset") != part:
        raise ValueError(f"records[{index}] source dataset does not match manifest")
    require_string(record.get("regulator_outcome"), f"records[{index}].regulator_outcome")
    for field in SUMMARY_FIELDS:
        value = record.get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"records[{index}].{field} must be a string or null")
    for field in ("denial_reason", "clinical_evidence", "prior_authorization"):
        if record.get(field) is not None:
            raise ValueError(f"records[{index}].{field} must remain null for CMS summaries")


def run_preflight(
    input_path: Path,
    manifest_path: Path,
    output_path: Path,
    entered_at: datetime,
) -> dict[str, Any]:
    require_outside_repository(input_path, "CMS summary input")
    require_outside_repository(manifest_path, "CMS summary manifest")
    manifest = json_object(manifest_path)
    expected_hash, expected_count = validate_manifest(manifest)
    actual_hash = sha256_file(input_path)
    if actual_hash != expected_hash:
        raise ValueError("CMS summary input hash does not match its extraction manifest")

    source = manifest["source"]
    part = require_string(source.get("part"), "manifest.source.part")
    if part not in DATASETS:
        raise ValueError("manifest.source.part is not a supported CMS dataset")

    deadlines = DeadlineCatalog.from_path(ROOT / "config" / "deadlines.yaml")
    machine = CaseStateMachine(deadlines)
    actor = Actor("cms-qic-summary-adapter", ActorKind.AGENT)
    decision_source = DecisionSource("deterministic", "cms-qic-summary-adapter", "0.1")
    evidence = EvidenceRef(
        "CMSQICSummaryExtraction",
        f"local-only://{input_path.name}",
        actual_hash,
    )
    outcome_counts: Counter[str] = Counter()
    appeal_type_counts: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    seen_case_ids: set[str] = set()
    cases_seen = 0

    with input_path.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"CMS summary input has a blank line at {index}")
            raw_record = json.loads(line)
            if not isinstance(raw_record, dict):
                raise ValueError(f"CMS summary record {index} must be an object")
            record = raw_record
            validate_record(record, index, part)
            case_id = require_hash(record["case_id"], f"records[{index}].case_id")
            if case_id in seen_case_ids:
                raise ValueError(f"duplicate CMS summary case_id at record {index}")
            seen_case_ids.add(case_id)
            outcome = require_string(record["regulator_outcome"], f"records[{index}].regulator_outcome")
            outcome_counts[outcome] += 1
            appeal_type = record.get("appeal_type")
            if isinstance(appeal_type, str) and appeal_type.strip():
                appeal_type_counts[appeal_type] += 1
            for field in SUMMARY_FIELDS:
                value = record.get(field)
                if isinstance(value, str) and value.strip():
                    field_counts[field] += 1

            case = machine.create(
                case_id=f"cms-qic:{case_id}",
                tenant_id="cms-qic-summary",
                entered_at=entered_at,
                actor=actor,
                source=decision_source,
            )
            case = machine.transition(
                case,
                CaseState.PARSE_FAILED_HUMAN_REVIEW,
                entered_at,
                actor,
                decision_source,
                "Appeal abstained: CMS supplies a regulator summary but not the original plan denial, clinical evidence, or original policy version.",
                (evidence,),
                f"cms-qic:{case_id}:summary-preflight",
            )
            state_counts[case.state.value] += 1
            cases_seen += 1

    if cases_seen != expected_count:
        raise ValueError(f"CMS summary record count mismatch: manifest={expected_count}, input={cases_seen}")

    return {
        "schema_version": "0.1",
        "status": "adapter_preflight_blocked",
        "recorded_at": datetime.now(UTC).date().isoformat(),
        "source_id": SOURCE_ID,
        "source": {
            "input_file_name": input_path.name,
            "input_sha256": actual_hash,
            "input_location": "local_only_outside_repository",
            "extraction_manifest": "outside_repository_only",
            "part": part,
            "record_count": cases_seen,
            "narrative_emitted_to_report": False,
        },
        "adapter_preflight": {
            "implemented": True,
            "version": "0.1",
            "state_machine_exercised": True,
            "state_machine_anchor": entered_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "anchor_is_case_date": False,
            "decision_source": decision_source.identifier,
            "cases_seen": cases_seen,
            "cases_abstained": cases_seen,
            "cases_ready_for_full_appeal": 0,
            "terminal_state_counts": dict(sorted(state_counts.items())),
            "blocking_reasons": {
                "missing_original_denial": cases_seen,
                "missing_original_denial_reason": cases_seen,
                "missing_clinical_evidence": cases_seen,
                "missing_original_policy_version": cases_seen,
                "prior_authorization_unverified": cases_seen,
            },
        },
        "summary_fields": {
            "nonempty_counts": dict(sorted(field_counts.items())),
            "interpretation": "aggregate_presence_only; narrative values remain outside the repository",
        },
        "regulator_outcomes": {
            "counts": dict(sorted(outcome_counts.items())),
            "field": "decision",
            "interpretation": "explicit_CMS_QIC_regulator_summary_outcome",
        },
        "appeal_types": {
            "counts": dict(sorted(appeal_type_counts.items())),
            "field": "appeal_type",
            "interpretation": "explicit_CMS_source_field; not inferred from denial_reason",
        },
        "comparison": {
            "status": "not_run",
            "compared_cases": 0,
            "matches": 0,
            "mismatches": 0,
            "reason": "No Appeal outcome exists because every summary row abstained before full Appeal inputs were available.",
        },
        "evaluation": {
            "adapter_preflight_completed": True,
            "summary_cases_evaluated": 0,
            "full_appeal_evaluation_completed": False,
            "full_appeal_cases_evaluated": 0,
            "regulator_ground_truth_comparisons": 0,
            "phase_9_hard_stop_started": False,
        },
    }


def parse_utc(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--entered-at must include a timezone")
    return parsed.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--entered-at",
        default="2026-08-28T00:00:00Z",
        help="fixed adapter anchor; this is not a case date (default: %(default)s)",
    )
    args = parser.parse_args()
    output_path = args.output.expanduser().resolve()
    report = run_preflight(
        args.input.expanduser().resolve(),
        args.manifest.expanduser().resolve(),
        output_path,
        parse_utc(args.entered_at),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "cases_seen": report["adapter_preflight"]["cases_seen"],
                "cases_abstained": report["adapter_preflight"]["cases_abstained"],
                "summary_cases_evaluated": report["evaluation"]["summary_cases_evaluated"],
                "full_appeal_cases_evaluated": report["evaluation"]["full_appeal_cases_evaluated"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
