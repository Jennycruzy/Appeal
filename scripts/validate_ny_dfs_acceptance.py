#!/usr/bin/env python3
"""Validate the NY DFS acceptance gates without reading case narratives."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "evidence" / "ny-dfs-acceptance.json"
DEFAULT_ACQUISITION = ROOT / "evidence" / "ny-dfs-export-acquisition.json"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def object_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def int_value(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest(
    manifest: dict[str, Any],
    acquisition: dict[str, Any],
    *,
    xlsx: Path | None = None,
    require_ready: bool = False,
) -> tuple[list[str], bool]:
    errors: list[str] = []
    acquisition_artifact = object_value(acquisition.get("artifact"))
    artifact = object_value(manifest.get("artifact"))
    if manifest.get("schema_version") != "0.1":
        errors.append("schema_version must be 0.1")
    if manifest.get("status") not in {"blocked", "accepted"}:
        errors.append("status must be blocked or accepted")
    if manifest.get("source_id") != "ny_dfs_external_appeal_archive":
        errors.append("source_id must be ny_dfs_external_appeal_archive")
    if artifact.get("file_name") != acquisition_artifact.get("file_name"):
        errors.append("artifact.file_name does not match acquisition evidence")
    if artifact.get("sha256") != acquisition_artifact.get("sha256"):
        errors.append("artifact.sha256 does not match acquisition evidence")
    if artifact.get("raw_artifact_location") != "local_download_only_not_repo":
        errors.append("raw artifact must remain local_download_only_not_repo")

    forbidden_keys = {
        "case_number",
        "case_records",
        "member_id",
        "narrative_values",
        "raw_rows",
        "raw_values",
        "records",
        "references",
        "summary_values",
    }

    def scan_keys(value: Any, path: str = "manifest") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if str(key).casefold() in forbidden_keys:
                    errors.append(f"{path}.{key} is not allowed in metadata-only manifest")
                scan_keys(nested, f"{path}.{key}")
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                scan_keys(nested, f"{path}[{index}]")

    scan_keys(manifest)

    field_policy = object_value(manifest.get("field_policy"))
    denial_reason = object_value(field_policy.get("denial_reason"))
    appeal_type = object_value(field_policy.get("appeal_type"))
    if denial_reason.get("source_column") != "Denial Reason":
        errors.append("denial_reason must remain bound to source column Denial Reason")
    if denial_reason.get("application_field") != "denial_reason":
        errors.append("denial_reason application field is required")
    if appeal_type.get("application_field") != "appeal_type":
        errors.append("appeal_type application field is required")

    gates = object_value(manifest.get("gates"))
    required_gates = {"source_integrity", "schema_mapping", "privacy", "reuse", "prior_authorization"}
    if set(gates) != required_gates:
        errors.append("gates must contain exactly source_integrity, schema_mapping, privacy, reuse, prior_authorization")

    source_gate = object_value(gates.get("source_integrity"))
    if source_gate.get("status") != "pass":
        errors.append("source_integrity gate is not passed")
    if not list_value(source_gate.get("evidence_refs")):
        errors.append("source_integrity requires evidence_refs")

    mapping = object_value(gates.get("schema_mapping"))
    if mapping.get("archive_filter") != "Appeal Type":
        errors.append("schema_mapping.archive_filter must be Appeal Type")
    if mapping.get("export_field") != "Denial Reason":
        errors.append("schema_mapping.export_field must be Denial Reason")
    mapping_ready = (
        mapping.get("status") == "verified"
        and mapping.get("mapping_decision") == "equivalent_verified"
        and mapping.get("verified_equivalent") is True
        and bool(list_value(mapping.get("evidence_refs")))
        and appeal_type.get("status") == "verified_mapping"
        and appeal_type.get("source_column") == "Denial Reason"
    )
    if not mapping_ready:
        if appeal_type.get("status") != "nullable_unverified" or appeal_type.get("source_column") is not None:
            errors.append("appeal_type must stay nullable and unverified until mapping evidence is accepted")

    privacy = object_value(gates.get("privacy"))
    expected_privacy = {
        "physical_address_shape": 140,
        "date_of_birth_label": 8,
        "member_id_label": 9,
    }
    if privacy.get("candidate_counts") != expected_privacy:
        errors.append("privacy candidate_counts must preserve the observed scan counts")
    privacy_ready = (
        privacy.get("status") in {"approved", "redacted"}
        and bool(string_value(privacy.get("reviewer")))
        and bool(string_value(privacy.get("reviewed_at")))
        and bool(list_value(privacy.get("evidence_refs")))
        and bool(string_value(privacy.get("decision")))
    )

    reuse = object_value(gates.get("reuse"))
    reuse_ready = (
        reuse.get("status") in {"permitted_for_local_evaluation", "permitted_for_evaluation_and_redistribution"}
        and bool(string_value(reuse.get("permission_source")))
        and bool(string_value(reuse.get("permission_reference")))
        and bool(list_value(reuse.get("evidence_refs")))
        and bool(string_value(reuse.get("reviewer")))
        and bool(string_value(reuse.get("reviewed_at")))
    )

    prior_auth = object_value(gates.get("prior_authorization"))
    accepted_count = int_value(prior_auth.get("accepted_count"))
    reviewed_count = int_value(prior_auth.get("reviewed_count"))
    prior_auth_ready = (
        prior_auth.get("status") == "reviewed"
        and bool(string_value(prior_auth.get("eligibility_basis")))
        and accepted_count > 0
        and reviewed_count == accepted_count
        and bool(HEX64.fullmatch(string_value(prior_auth.get("selection_fingerprint"))))
        and bool(list_value(prior_auth.get("evidence_refs")))
        and bool(string_value(prior_auth.get("reviewer")))
        and bool(string_value(prior_auth.get("reviewed_at")))
    )

    acceptance = object_value(manifest.get("acceptance"))
    acceptance_ready = (
        acceptance.get("decision") == "ready_for_local_evaluation"
        and acceptance.get("accepted_for_local_evaluation") is True
        and int_value(acceptance.get("accepted_record_count")) == accepted_count
        and accepted_count > 0
    )
    all_gates_ready = mapping_ready and privacy_ready and reuse_ready and prior_auth_ready and acceptance_ready
    if manifest.get("status") == "accepted" and not all_gates_ready:
        errors.append("status accepted is inconsistent with unresolved acceptance gates")
    ready = manifest.get("status") == "accepted" and all_gates_ready and not errors

    if xlsx is not None:
        resolved_xlsx = xlsx.expanduser().resolve()
        try:
            resolved_xlsx.relative_to(ROOT.resolve())
            errors.append("raw workbook must be outside the repository")
        except ValueError:
            pass
        if not resolved_xlsx.is_file():
            errors.append(f"raw workbook does not exist: {resolved_xlsx}")
        elif sha256_file(resolved_xlsx) != string_value(acquisition_artifact.get("sha256")):
            errors.append("raw workbook SHA-256 does not match acquisition evidence")

    if require_ready and not ready:
        errors.append("acceptance manifest is not ready; no real evaluation is permitted")
    return errors, ready


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--acquisition", type=Path, default=DEFAULT_ACQUISITION)
    parser.add_argument("--xlsx", type=Path)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    acquisition = load_json(args.acquisition)
    errors, ready = validate_manifest(
        manifest,
        acquisition,
        xlsx=args.xlsx,
        require_ready=args.require_ready,
    )
    result = {
        "status": "ready" if ready else "blocked",
        "errors": errors,
        "manifest": str(args.manifest),
        "require_ready": args.require_ready,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
