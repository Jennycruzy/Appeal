"""Measure the local security fallback on synthetic labeled fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from appeal_agents import LocalSecurityBoundary, default_local_security_cases, measure_security_boundary


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evidence" / "local-security-fallback-measurement.json"


def main() -> int:
    measurement = measure_security_boundary(
        LocalSecurityBoundary(),
        default_local_security_cases(),
        provider="local_deterministic_fallback",
    )
    report = {
        "schema_version": "0.1",
        "scope": "synthetic local fallback only",
        "model_armor_or_gemma_run": False,
        "measurement": measurement.to_public_json(),
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Aggregate report: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
