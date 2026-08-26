#!/usr/bin/env python3
"""Record metadata and a fingerprint for a Synthea FHIR corpus.

Patient-level FHIR bundles remain outside the repository.  This command records
only aggregate resource counts, code distributions, and hashes of the local
generated files.  A second output directory may be supplied to prove that the
same pinned generator, seed, and reference date produce identical bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast


ROOT: Final[Path] = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH: Final[Path] = ROOT / "config" / "requirements.json"

JsonPrimitive = None | bool | int | float | str
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]


def load_object(path: Path) -> JsonObject:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return cast(JsonObject, value)


def string_value(value: JsonValue | None) -> str:
    return value if isinstance(value, str) else ""


def int_value(value: JsonValue | None) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def object_value(value: JsonValue | None) -> JsonObject:
    return value if isinstance(value, dict) else {}


def list_value(value: JsonValue | None) -> list[JsonValue]:
    return value if isinstance(value, list) else []


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inspect_output(
    input_dir: Path,
) -> tuple[dict[str, str], int, Counter[str], Counter[tuple[str, str, str]]]:
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Synthea output directory does not exist: {input_dir}")
    fhir_dir = input_dir / "fhir"
    if not fhir_dir.is_dir():
        raise FileNotFoundError(f"Synthea FHIR directory does not exist: {fhir_dir}")
    files = sorted(path for path in fhir_dir.glob("*.json") if path.is_file())
    if not files:
        raise ValueError(f"no JSON FHIR output found in {fhir_dir}")
    file_hashes: dict[str, str] = {}
    bundles = 0
    resources: Counter[str] = Counter()
    conditions: Counter[tuple[str, str, str]] = Counter()
    for path in files:
        raw = path.read_bytes()
        value = json.loads(raw)
        if not isinstance(value, dict):
            continue
        bundle = cast(JsonObject, value)
        if string_value(bundle.get("resourceType")) != "Bundle":
            continue
        entries = list_value(bundle.get("entry"))
        has_patient = any(
            string_value(object_value(object_value(entry).get("resource")).get("resourceType")) == "Patient"
            for entry in entries
            if isinstance(entry, dict)
        )
        if not has_patient:
            continue
        file_hashes[str(path.relative_to(input_dir))] = sha256_bytes(raw)
        bundles += 1
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            resource = object_value(entry.get("resource"))
            resource_type = string_value(resource.get("resourceType"))
            if not resource_type:
                continue
            resources[resource_type] += 1
            if resource_type != "Condition":
                continue
            code = object_value(resource.get("code"))
            codings = list_value(code.get("coding"))
            if not codings:
                conditions[("", "", string_value(code.get("text")))] += 1
                continue
            first = object_value(codings[0])
            conditions[
                (
                    string_value(first.get("system")),
                    string_value(first.get("code")),
                    string_value(first.get("display")) or string_value(code.get("text")),
                )
            ] += 1
    if bundles == 0:
        raise ValueError("no patient FHIR bundles were found")
    return file_hashes, bundles, resources, conditions


def corpus_fingerprint(file_hashes: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for relative_path in sorted(file_hashes):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hashes[relative_path].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def compare_hashes(first: dict[str, str], second: dict[str, str]) -> JsonObject:
    first_paths = set(first)
    second_paths = set(second)
    missing_from_second = sorted(first_paths - second_paths)
    extra_in_second = sorted(second_paths - first_paths)
    changed = sorted(path for path in first_paths & second_paths if first[path] != second[path])
    identical = not missing_from_second and not extra_in_second and not changed
    return {
        "identical": identical,
        "missing_from_second": missing_from_second,
        "extra_in_second": extra_in_second,
        "changed_files": changed,
    }


def build_manifest(
    input_dir: Path,
    *,
    compare_dir: Path | None,
    requirements: JsonObject,
) -> JsonObject:
    synthea = object_value(requirements.get("synthea"))
    file_hashes, bundle_count, resource_counts, conditions = inspect_output(input_dir)
    comparison: JsonObject | None = None
    if compare_dir is not None:
        second_hashes, _, _, _ = inspect_output(compare_dir)
        comparison = compare_hashes(file_hashes, second_hashes)
        if comparison.get("identical") is not True:
            raise ValueError(f"Synthea regeneration was not byte-identical: {json.dumps(comparison)}")

    condition_values: list[JsonValue] = []
    for (system, code, display), count in sorted(conditions.items()):
        condition_values.append({"system": system, "code": code, "display": display, "count": count})
    manifest: JsonObject = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "synthetic_only": True,
        "generator": {
            "name": "Synthea",
            "version": string_value(synthea.get("version")),
            "release_commit": string_value(synthea.get("release_commit")),
            "asset_name": string_value(synthea.get("asset_name")),
            "asset_sha256": string_value(synthea.get("asset_sha256")),
            "seed": int_value(synthea.get("seed")),
            "clinician_seed": int_value(synthea.get("clinician_seed")),
            "population_requested": int_value(synthea.get("population")),
            "state": string_value(synthea.get("state")),
            "reference_date": string_value(synthea.get("reference_date")),
            "end_date": string_value(synthea.get("end_date")),
            "thread_pool_size": int_value(synthea.get("thread_pool_size")),
        },
        "source_output": str(input_dir.relative_to(ROOT)) if input_dir.is_relative_to(ROOT) else "local-cache",
        "patient_bundle_count": bundle_count,
        "resource_counts": dict(sorted(resource_counts.items())),
        "condition_distribution": condition_values,
        "fhir_file_count": len(file_hashes),
        "bundle_set_fingerprint": corpus_fingerprint(file_hashes),
        "tracked_file_hashes": file_hashes,
    }
    if comparison is not None:
        manifest["regeneration_comparison"] = comparison
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--compare-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    requirements = load_object(REQUIREMENTS_PATH)
    manifest = build_manifest(args.input_dir, compare_dir=args.compare_dir, requirements=requirements)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: manifest[key] for key in ["patient_bundle_count", "resource_counts", "bundle_set_fingerprint"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
