#!/usr/bin/env python3
"""Inspect the aggregate evidence distribution of the pinned Synthea corpus.

The report is deliberately aggregate-only.  It validates the manifest-tracked
patient bundles and records resource coverage, coded/value-bearing counts, and
status counts without emitting patient identifiers or narrative content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any, Final


ROOT: Final[Path] = Path(__file__).resolve().parents[1]
MANIFEST_PATH: Final[Path] = ROOT / "evidence" / "corpus.json"
EVIDENCE_TYPES: Final[tuple[str, ...]] = (
    "AllergyIntolerance",
    "Condition",
    "Observation",
    "Procedure",
    "DiagnosticReport",
    "ImagingStudy",
    "Medication",
    "MedicationRequest",
    "MedicationAdministration",
    "CarePlan",
    "CareTeam",
    "Encounter",
    "DocumentReference",
    "Claim",
    "ExplanationOfBenefit",
)
EVIDENCE_ROLES: Final[dict[str, tuple[str, ...]]] = {
    "clinical_findings": ("Condition", "Observation", "DiagnosticReport", "ImagingStudy"),
    "treatment_history": (
        "Procedure",
        "Medication",
        "MedicationRequest",
        "MedicationAdministration",
        "CarePlan",
    ),
    "care_context": ("Encounter", "CareTeam", "DocumentReference", "AllergyIntolerance"),
    "utilization_and_claims": ("Claim", "ExplanationOfBenefit"),
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def object_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def hash_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def distribution(values: list[int], count_label: str) -> dict[str, int | float]:
    if not values:
        return {count_label: 0, "min": 0, "median": 0, "mean": 0, "max": 0}
    return {
        count_label: len(values),
        "min": min(values),
        "median": median(values),
        "mean": round(mean(values), 2),
        "max": max(values),
    }


def inspect(input_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Synthea output directory does not exist: {input_dir}")
    tracked = manifest.get("tracked_file_hashes")
    if not isinstance(tracked, dict) or not tracked:
        raise ValueError("corpus manifest has no tracked_file_hashes object")

    resource_counts: Counter[str] = Counter()
    coded_counts: Counter[str] = Counter()
    value_counts: Counter[str] = Counter()
    status_counts: dict[str, Counter[str]] = defaultdict(Counter)
    per_patient: dict[str, Counter[str]] = {}
    entry_counts: list[int] = []

    for relative, expected_hash in sorted(tracked.items()):
        if not isinstance(relative, str) or not isinstance(expected_hash, str):
            raise ValueError("manifest file hashes must map string paths to string hashes")
        path = input_dir / relative
        if not path.is_file():
            raise FileNotFoundError(f"manifest-tracked file is missing: {path}")
        raw = path.read_bytes()
        if hash_bytes(raw) != expected_hash:
            raise ValueError(f"manifest hash mismatch: {relative}")
        bundle = load_object_from_bytes(raw, relative)
        if bundle.get("resourceType") != "Bundle" or bundle.get("type") != "transaction":
            raise ValueError(f"manifest file is not a transaction Bundle: {relative}")
        entries = list_value(bundle.get("entry"))
        patients = [
            object_value(object_value(entry).get("resource"))
            for entry in entries
            if object_value(object_value(entry).get("resource")).get("resourceType") == "Patient"
        ]
        if len(patients) != 1 or not isinstance(patients[0].get("id"), str):
            raise ValueError(f"expected one identified Patient resource: {relative}")
        patient_id = patients[0]["id"]
        if patient_id in per_patient:
            raise ValueError(f"duplicate Patient bundle: {relative}")
        counts: Counter[str] = Counter()
        entry_counts.append(len(entries))
        for entry in entries:
            resource = object_value(object_value(entry).get("resource"))
            resource_type = resource.get("resourceType")
            if not isinstance(resource_type, str) or not resource_type:
                continue
            resource_counts[resource_type] += 1
            counts[resource_type] += 1
            if resource.get("code") or resource.get("type") or resource.get("medicationCodeableConcept") or resource.get("medicationReference"):
                coded_counts[resource_type] += 1
            if any(key.startswith("value") for key in resource):
                value_counts[resource_type] += 1
            status = resource.get("status")
            if isinstance(status, str):
                status_counts[resource_type][status] += 1
        per_patient[patient_id] = counts

    expected_counts = manifest.get("resource_counts")
    if not isinstance(expected_counts, dict):
        raise ValueError("corpus manifest has no resource_counts object")
    normalized_expected = {
        key: value
        for key, value in expected_counts.items()
        if isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool)
    }
    if dict(sorted(resource_counts.items())) != dict(sorted(normalized_expected.items())):
        raise ValueError("aggregate resource counts do not match corpus manifest")

    coverage: dict[str, dict[str, int | float]] = {}
    for resource_type in EVIDENCE_TYPES:
        values = [counts.get(resource_type, 0) for counts in per_patient.values()]
        row = distribution(values, "patients_total")
        row["patients_with_resource"] = sum(value > 0 for value in values)
        coverage[resource_type] = row
    return {
        "schema_version": 1,
        "generated_at": now_iso(),
        "synthetic_only": True,
        "input_manifest": {
            "patient_bundle_count": manifest.get("patient_bundle_count"),
            "bundle_set_fingerprint": manifest.get("bundle_set_fingerprint"),
        },
        "bundle_count": len(per_patient),
        "entry_count": distribution(entry_counts, "bundles"),
        "resource_counts": dict(sorted(resource_counts.items())),
        "patient_coverage": coverage,
        "coded_resource_counts": dict(sorted(coded_counts.items())),
        "value_bearing_resource_counts": dict(sorted(value_counts.items())),
        "status_counts": {
            resource_type: dict(sorted(counts.items()))
            for resource_type, counts in sorted(status_counts.items())
        },
        "evidence_roles": {key: list(value) for key, value in EVIDENCE_ROLES.items()},
        "interpretation": {
            "purpose": "availability and distribution review for synthetic chart retrieval",
            "policy_criterion_sufficiency": "not established by this aggregate report",
            "real_denial_ground_truth": False,
            "patient_identifiers_or_narrative_emitted": False,
        },
    }


def load_object_from_bytes(raw: bytes, label: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {label}")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_object(MANIFEST_PATH)
    report = inspect(args.input_dir, manifest)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "bundle_count": report["bundle_count"],
                "resource_counts": report["resource_counts"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
