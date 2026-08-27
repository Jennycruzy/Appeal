#!/usr/bin/env python3
"""Verify aggregate resource counts in a local HAPI FHIR corpus load."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT: Final[Path] = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH: Final[Path] = ROOT / "config" / "requirements.json"
MANIFEST_PATH: Final[Path] = ROOT / "evidence" / "corpus.json"


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def string_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def object_value(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def query_json(url: str, timeout: float) -> dict[str, object]:
    request = Request(url=url, headers={"Accept": "application/fhir+json"}, method="GET")
    with urlopen(request, timeout=timeout) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise ValueError(f"HAPI returned a non-object response for {url}")
    return value


def count_resource(base_url: str, resource_type: str, timeout: float) -> int:
    value = query_json(f"{base_url.rstrip('/')}/{resource_type}?_summary=count", timeout)
    total = value.get("total")
    if not isinstance(total, int) or isinstance(total, bool):
        raise ValueError(f"HAPI count response for {resource_type} did not contain an integer total")
    return total


def write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    requirements = load_object(REQUIREMENTS_PATH)
    hapi = object_value(requirements.get("hapi"))
    base_url = args.base_url or string_value(hapi.get("base_url")) or "http://127.0.0.1:8080/fhir"
    manifest = load_object(MANIFEST_PATH)
    expected_value = manifest.get("resource_counts")
    if not isinstance(expected_value, dict):
        raise ValueError("corpus manifest has no resource_counts object")
    expected = {
        key: value
        for key, value in expected_value.items()
        if isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool)
    }

    report: dict[str, object] = {
        "schema_version": 1,
        "status": "running",
        "checked_at": now_iso(),
        "base_url": base_url,
        "expected_patient_bundle_count": manifest.get("patient_bundle_count"),
        "expected_resource_counts": expected,
    }
    try:
        metadata = query_json(base_url.rstrip("/") + "/metadata", args.timeout)
        observed: dict[str, int] = {}
        for resource_type in sorted(expected):
            observed[resource_type] = count_resource(base_url, resource_type, args.timeout)
        observed["Practitioner"] = count_resource(base_url, "Practitioner", args.timeout)
    except (HTTPError, OSError, URLError, TimeoutError, ValueError) as error:
        report.update({"status": "blocked", "error": type(error).__name__, "finished_at": now_iso()})
        write_report(args.report, report)
        print(f"HAPI verification failed: {type(error).__name__}", file=sys.stderr)
        return 2

    mismatches = {
        resource_type: {"expected": expected[resource_type], "observed": observed[resource_type]}
        for resource_type in expected
        if observed[resource_type] != expected[resource_type]
    }
    report.update(
        {
            "status": "pass" if not mismatches else "blocked",
            "server_fhir_version": string_value(metadata.get("fhirVersion")),
            "server_software": object_value(metadata.get("software")),
            "observed_resource_counts": observed,
            "unexpected_resource_counts": {
                key: value for key, value in observed.items() if key not in expected and value != 0
            },
            "mismatches": mismatches,
            "finished_at": now_iso(),
        }
    )
    write_report(args.report, report)
    if mismatches:
        print("HAPI resource count verification failed", file=sys.stderr)
        return 2
    print(json.dumps({"status": report["status"], "observed_resource_counts": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
