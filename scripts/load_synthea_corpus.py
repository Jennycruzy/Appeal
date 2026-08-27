#!/usr/bin/env python3
"""Load local Synthea transaction bundles into a running HAPI FHIR server.

The source bundles remain local and are never copied into the repository.  The
report contains only aggregate counts, HTTP statuses, and the corpus manifest
fingerprint.  A transaction failure stops the import and records the partial
count so an operator does not mistake a partial load for a complete corpus.
"""

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
MANIFEST_PATH: Final[Path] = ROOT / "evidence" / "corpus.json"


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def is_patient_transaction_bundle(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("resourceType") != "Bundle" or value.get("type") != "transaction":
        return False
    entries = value.get("entry")
    if not isinstance(entries, list):
        return False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        resource = entry.get("resource")
        if isinstance(resource, dict) and resource.get("resourceType") == "Patient":
            return True
    return False


def tracked_paths(input_dir: Path, manifest: dict[str, object]) -> list[Path]:
    fhir_dir = input_dir / "fhir"
    if not fhir_dir.is_dir():
        raise FileNotFoundError(f"FHIR directory does not exist: {fhir_dir}")

    tracked = manifest.get("tracked_file_hashes")
    if isinstance(tracked, dict) and tracked:
        paths: list[Path] = []
        for relative in sorted(key for key in tracked if isinstance(key, str)):
            path = input_dir / relative
            if not path.is_file():
                raise FileNotFoundError(f"manifest-tracked FHIR file is missing: {path}")
            paths.append(path)
        return paths
    return sorted(path for path in fhir_dir.glob("*.json") if path.is_file())


def post_bundle(base_url: str, raw: bytes, timeout: float) -> tuple[int | None, str | None]:
    request = Request(
        url=base_url.rstrip("/") + "/",
        data=raw,
        headers={
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            response.read()
            return response.status, None
    except HTTPError as error:
        error.read(4096)
        return error.code, "HTTPError"
    except (TimeoutError, URLError, OSError) as error:
        return None, type(error).__name__


def write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/fhir")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument(
        "--start-index",
        type=int,
        default=1,
        help="1-based manifest index to start at; use only after reconciling a partial load",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started_at = now_iso()
    manifest = load_object(MANIFEST_PATH) if MANIFEST_PATH.is_file() else {}
    report: dict[str, object] = {
        "schema_version": 1,
        "status": "running",
        "started_at": started_at,
        "base_url": args.base_url,
        "fhir_version": "R4",
        "input_manifest": {
            "patient_bundle_count": manifest.get("patient_bundle_count"),
            "bundle_set_fingerprint": manifest.get("bundle_set_fingerprint"),
        },
        "start_index": args.start_index,
        "accepted_bundle_count": 0,
        "accepted_this_run_count": 0,
        "http_status_counts": {},
    }

    try:
        paths = tracked_paths(args.input_dir, manifest)
    except (FileNotFoundError, ValueError) as error:
        report.update({"status": "blocked", "error": str(error), "finished_at": now_iso()})
        write_report(args.report, report)
        print(str(error), file=sys.stderr)
        return 2

    if args.start_index < 1 or args.start_index > len(paths):
        message = f"start index must be between 1 and {len(paths)}"
        report.update({"status": "blocked", "error": message, "finished_at": now_iso()})
        write_report(args.report, report)
        print(message, file=sys.stderr)
        return 2

    report["candidate_file_count"] = len(paths)
    report["remaining_file_count"] = len(paths) - args.start_index + 1
    status_counts: dict[str, int] = {}
    accepted = args.start_index - 1
    accepted_this_run = 0
    for index, path in enumerate(paths[args.start_index - 1 :], start=args.start_index):
        try:
            raw = path.read_bytes()
            value = json.loads(raw)
        except (OSError, json.JSONDecodeError) as error:
            report.update(
                {
                    "status": "blocked",
                    "failed_index": index,
                    "failure": type(error).__name__,
                    "accepted_bundle_count": accepted,
                    "accepted_this_run_count": accepted_this_run,
                    "http_status_counts": status_counts,
                    "finished_at": now_iso(),
                }
            )
            write_report(args.report, report)
            print(f"bundle {index} could not be read or parsed: {type(error).__name__}", file=sys.stderr)
            return 2

        if not is_patient_transaction_bundle(value):
            report.update(
                {
                    "status": "blocked",
                    "failed_index": index,
                    "failure": "not_a_patient_transaction_bundle",
                    "accepted_bundle_count": accepted,
                    "accepted_this_run_count": accepted_this_run,
                    "http_status_counts": status_counts,
                    "finished_at": now_iso(),
                }
            )
            write_report(args.report, report)
            print(f"bundle {index} is not a patient transaction bundle", file=sys.stderr)
            return 2

        status, error_name = post_bundle(args.base_url, raw, args.timeout)
        if status is None or not 200 <= status < 300:
            report.update(
                {
                    "status": "blocked",
                    "failed_index": index,
                    "failure_http_status": status,
                    "failure": error_name or "non_success_http_status",
                    "accepted_bundle_count": accepted,
                    "accepted_this_run_count": accepted_this_run,
                    "http_status_counts": status_counts,
                    "finished_at": now_iso(),
                }
            )
            write_report(args.report, report)
            print(f"bundle {index} failed with HTTP {status}: {error_name or 'unknown error'}", file=sys.stderr)
            return 2

        accepted += 1
        accepted_this_run += 1
        status_key = str(status)
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
        if accepted == args.start_index or accepted % 10 == 0 or accepted == len(paths):
            print(f"loaded {accepted}/{len(paths)} transaction bundles", flush=True)

    report.update(
        {
            "status": "pass",
            "accepted_bundle_count": accepted,
            "accepted_this_run_count": accepted_this_run,
            "http_status_counts": status_counts,
            "finished_at": now_iso(),
        }
    )
    write_report(args.report, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
