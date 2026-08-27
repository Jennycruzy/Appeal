#!/usr/bin/env python3
"""Run the fail-closed Oregon local adapter preflight.

The Oregon workbook supplies an external-review outcome and limited case
metadata, but it does not supply the denial narrative, a policy reference, or
clinical evidence required by Appeal. This command therefore exercises the
real case state machine and records a human-review abstention for each
accepted row. It deliberately does not turn treatment text into denial text,
does not manufacture an Appeal outcome, and does not calculate a comparison
score.

The input contains free text and must remain outside the repository. The
output is aggregate-only evidence and contains no case references or text.
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
DEFAULT_INPUT = ROOT.parent / "Downloads" / "oregon-iro-local-evaluation.json"
DEFAULT_MANIFEST = ROOT / "evidence" / "oregon-acceptance.json"
DEFAULT_OUTPUT = ROOT / "evidence" / "oregon-evaluation.json"
HASH_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
REGULATOR_OUTCOMES: Final[frozenset[str]] = frozenset(
    {"upheld_denial", "overturned_denial", "partial_overturn"}
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


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
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def require_nonnegative_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def parse_utc(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--entered-at must include a timezone")
    return parsed.astimezone(UTC)


def validate_acceptance(manifest: dict[str, Any]) -> tuple[str, int]:
    if manifest.get("source_id") != "oregon_dfr_iro_case_detail_report":
        raise ValueError("acceptance manifest source_id is not the Oregon IRO report")
    acceptance = manifest.get("acceptance")
    if not isinstance(acceptance, dict) or acceptance.get("accepted_for_local_evaluation") is not True:
        raise ValueError("Oregon acceptance manifest does not authorize local evaluation")
    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict):
        raise ValueError("acceptance manifest artifact is missing")
    source_hash = require_hash(artifact.get("sha256"), "acceptance artifact.sha256")
    scope = manifest.get("scope")
    if not isinstance(scope, dict):
        raise ValueError("acceptance manifest scope is missing")
    expected_count = require_nonnegative_int(scope.get("accepted_local_rows"), "scope.accepted_local_rows")
    if scope.get("prior_authorization_claimed") is not False:
        raise ValueError("Oregon local evaluation must not claim prior authorization")
    return source_hash, expected_count


def validate_input(document: dict[str, Any], expected_source_hash: str, expected_count: int) -> list[dict[str, Any]]:
    if document.get("status") != "local_only_ready_for_appeal_adapter":
        raise ValueError("Oregon local input is not marked ready for the adapter")
    if document.get("source_id") != "oregon_dfr_iro_case_detail_report":
        raise ValueError("local input source_id is not the Oregon IRO report")

    source_workbook = document.get("source_workbook")
    if not isinstance(source_workbook, dict):
        raise ValueError("local input source_workbook is missing")
    if require_hash(source_workbook.get("sha256"), "local input source_workbook.sha256") != expected_source_hash:
        raise ValueError("local input source workbook hash does not match acceptance manifest")
    if source_workbook.get("raw_artifact_location") != "local_download_only_not_repo":
        raise ValueError("local input must identify the raw workbook as outside the repository")

    scope = document.get("scope")
    if not isinstance(scope, dict) or scope.get("prior_authorization_claimed") is not False:
        raise ValueError("local input must not claim prior authorization")
    record_count = require_nonnegative_int(scope.get("record_count"), "local input scope.record_count")
    if record_count != expected_count:
        raise ValueError(f"local input record count mismatch: manifest={expected_count}, input={record_count}")

    raw_records = document.get("records")
    if not isinstance(raw_records, list):
        raise ValueError("local input records must be an array")
    if len(raw_records) != expected_count:
        raise ValueError(f"local input records length mismatch: expected={expected_count}, observed={len(raw_records)}")

    records: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    for index, raw_record in enumerate(raw_records, start=1):
        if not isinstance(raw_record, dict):
            raise ValueError(f"local input record {index} must be an object")
        source_ref = require_hash(raw_record.get("source_case_ref"), f"records[{index}].source_case_ref")
        if source_ref in seen_refs:
            raise ValueError(f"duplicate source_case_ref at record {index}")
        seen_refs.add(source_ref)
        source_row = raw_record.get("source_row")
        if not isinstance(source_row, int) or isinstance(source_row, bool) or source_row <= 0:
            raise ValueError(f"records[{index}].source_row must be a positive integer")
        outcome = require_string(raw_record.get("regulator_outcome"), f"records[{index}].regulator_outcome")
        if outcome not in REGULATOR_OUTCOMES:
            raise ValueError(f"records[{index}].regulator_outcome is not an accepted Oregon outcome")
        if raw_record.get("denial_reason") is not None:
            raise ValueError("Oregon adapter cannot accept a populated denial_reason")
        if raw_record.get("appeal_type") is not None:
            raise ValueError("Oregon adapter cannot accept a populated appeal_type")
        if not isinstance(raw_record.get("treatment_text"), str):
            raise ValueError(f"records[{index}].treatment_text must be a string")
        records.append(raw_record)
    return records


def run_preflight(
    input_path: Path,
    manifest_path: Path,
    output_path: Path,
    entered_at: datetime,
) -> dict[str, Any]:
    require_outside_repository(input_path, "local Oregon evaluation input")
    manifest = json_object(manifest_path)
    expected_source_hash, expected_count = validate_acceptance(manifest)
    document = json_object(input_path)
    records = validate_input(document, expected_source_hash, expected_count)
    input_hash = sha256_file(input_path)

    deadlines = DeadlineCatalog.from_path(ROOT / "config" / "deadlines.yaml")
    machine = CaseStateMachine(deadlines)
    actor = Actor("oregon-local-evaluation-adapter", ActorKind.AGENT)
    source = DecisionSource("deterministic", "oregon-local-evaluation-adapter", "0.1")
    evidence = EvidenceRef("OregonLocalEvaluationInput", "local-only://oregon-iro-local-evaluation.json", input_hash)
    outcome_counts = Counter(require_string(record["regulator_outcome"], "regulator outcome") for record in records)
    state_counts: Counter[str] = Counter()

    for record in records:
        case_id = f"oregon-iro:{require_hash(record['source_case_ref'], 'source_case_ref')}"
        case = machine.create(case_id, "oregon-iro-local", entered_at, actor, source)
        case = machine.transition(
            case,
            CaseState.PARSE_FAILED_HUMAN_REVIEW,
            entered_at,
            actor,
            source,
            "Appeal abstained: the regulator row has no denial narrative or denial reason to parse.",
            (evidence,),
            f"{case_id}:parse",
        )
        state_counts[case.state.value] += 1

    count = len(records)
    return {
        "schema_version": "0.1",
        "status": "adapter_preflight_blocked",
        "recorded_at": datetime.now(UTC).date().isoformat(),
        "source_id": "oregon_dfr_iro_case_detail_report",
        "source": {
            "input_file_name": input_path.name,
            "input_sha256": input_hash,
            "raw_workbook_sha256": expected_source_hash,
            "input_location": "local_only_outside_repository",
            "acceptance_manifest": "evidence/oregon-acceptance.json",
            "record_count": count,
            "free_text_emitted_to_report": False,
        },
        "adapter_preflight": {
            "implemented": True,
            "version": "0.1",
            "state_machine_exercised": True,
            "state_machine_anchor": entered_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "anchor_is_case_date": False,
            "decision_source": source.identifier,
            "cases_seen": count,
            "cases_abstained": count,
            "cases_ready_for_full_appeal": 0,
            "terminal_state_counts": dict(sorted(state_counts.items())),
            "blocking_reasons": {
                "missing_denial_narrative": count,
                "missing_denial_reason": count,
                "missing_policy_reference": count,
                "missing_clinical_evidence": count,
                "prior_authorization_unverified": count,
            },
        },
        "regulator_outcomes": {
            "counts": dict(sorted(outcome_counts.items())),
            "field": "Case Outcome",
            "interpretation": "observed_regulator_outcome_only",
        },
        "comparison": {
            "status": "not_run",
            "appeal_outcome_field_present": False,
            "compared_cases": 0,
            "matches": 0,
            "mismatches": 0,
            "reason": "No Appeal outcome exists because every row abstained before denial parsing.",
        },
        "evaluation": {
            "adapter_preflight_completed": True,
            "full_appeal_evaluation_completed": False,
            "appeal_cases_evaluated": 0,
            "regulator_ground_truth_comparisons": 0,
            "phase_9_hard_stop_started": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--entered-at",
        default="2026-08-27T00:00:00Z",
        help="fixed adapter anchor; this is not a case date (default: %(default)s)",
    )
    args = parser.parse_args()
    report = run_preflight(
        args.input.expanduser().resolve(),
        args.manifest.expanduser().resolve(),
        args.output.expanduser().resolve(),
        parse_utc(args.entered_at),
    )
    args.output.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.expanduser().resolve().write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "cases_seen": report["adapter_preflight"]["cases_seen"],
                "cases_abstained": report["adapter_preflight"]["cases_abstained"],
                "appeal_cases_evaluated": report["evaluation"]["appeal_cases_evaluated"],
                "regulator_ground_truth_comparisons": report["evaluation"]["regulator_ground_truth_comparisons"],
                "output": str(args.output.expanduser().resolve()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
