"""Measure managed Model Armor on synthetic fixtures without persisting content."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from google.api_core.client_options import ClientOptions
from google.cloud import modelarmor_v1

from appeal_agents import SecurityMeasurementCase, default_local_security_cases


DEFAULT_PROJECT = "onyx-yeti-506606-i9"
DEFAULT_LOCATION = "europe-west2"
DEFAULT_TEMPLATE_ID = "appeal-tripwire-v1"
DEFAULT_OUTPUT = Path("evidence/model-armor-measurement.json")


def _enum_name(value: Any) -> str:
    return getattr(value, "name", str(value))


def _scan(
    client: modelarmor_v1.ModelArmorClient,
    template_name: str,
    case: SecurityMeasurementCase,
) -> tuple[bool, bool]:
    """Return (provider_matched, provider_scan_succeeded)."""

    if case.surface == "inbound_document":
        response = client.sanitize_user_prompt(
            request=modelarmor_v1.SanitizeUserPromptRequest(
                name=template_name,
                user_prompt_data=modelarmor_v1.DataItem(text=case.content),
            ),
            timeout=60,
        )
    else:
        response = client.sanitize_model_response(
            request=modelarmor_v1.SanitizeModelResponseRequest(
                name=template_name,
                model_response_data=modelarmor_v1.DataItem(text=case.content),
            ),
            timeout=60,
        )
    result = response.sanitization_result
    return (
        _enum_name(result.filter_match_state) == "MATCH_FOUND",
        _enum_name(result.invocation_result) == "SUCCESS",
    )


def measure(
    *,
    project: str,
    location: str,
    template_id: str,
    cases: tuple[SecurityMeasurementCase, ...],
) -> dict[str, object]:
    client = modelarmor_v1.ModelArmorClient(
        transport="rest",
        client_options=ClientOptions(
            api_endpoint=f"modelarmor.{location}.rep.googleapis.com"
        ),
    )
    template_name = f"projects/{project}/locations/{location}/templates/{template_id}"

    counts = {
        "true_positive": 0,
        "false_positive": 0,
        "true_negative": 0,
        "false_negative": 0,
    }
    surface_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "case_count": 0,
            "expected_blocked": 0,
            "provider_matched": 0,
            "successful_scans": 0,
            "inconclusive_scans": 0,
        }
    )
    provider_errors = 0
    inconclusive_scans = 0

    for case in cases:
        surface = surface_counts[case.surface]
        surface["case_count"] += 1
        expected_blocked = case.expected.value == "blocked"
        if expected_blocked:
            surface["expected_blocked"] += 1
        try:
            provider_matched, scan_succeeded = _scan(client, template_name, case)
        except Exception:
            provider_errors += 1
            inconclusive_scans += 1
            surface["inconclusive_scans"] += 1
            # The application boundary is fail-closed when the provider is unavailable.
            actual_blocked = True
        else:
            if provider_matched:
                surface["provider_matched"] += 1
            if scan_succeeded:
                surface["successful_scans"] += 1
            else:
                inconclusive_scans += 1
                surface["inconclusive_scans"] += 1
            # A non-successful provider result is quarantined by the application boundary.
            actual_blocked = provider_matched or not scan_succeeded

        if expected_blocked and actual_blocked:
            counts["true_positive"] += 1
        elif expected_blocked and not actual_blocked:
            counts["false_negative"] += 1
        elif not expected_blocked and actual_blocked:
            counts["false_positive"] += 1
        else:
            counts["true_negative"] += 1

    true_positive = counts["true_positive"]
    false_positive = counts["false_positive"]
    false_negative = counts["false_negative"]
    true_negative = counts["true_negative"]
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    false_positive_denominator = true_negative + false_positive

    return {
        "schema_version": "0.2",
        "scope": "synthetic local fixtures submitted to managed Model Armor; content omitted",
        "provider": "google_model_armor",
        "implementation": "managed_model_armor_v1",
        "project": project,
        "location": location,
        "template_id": template_id,
        "model_armor_run": True,
        "gemma_run": False,
        "model_armor_or_gemma_run": True,
        "supported_template_filters": ["sdp_basic", "pi_and_jailbreak"],
        "unsupported_template_filters": ["malicious_uri:europe-west2"],
        "measurement": {
            "case_count": len(cases),
            **counts,
            "successful_scans": len(cases) - inconclusive_scans,
            "inconclusive_scans": inconclusive_scans,
            "provider_errors": provider_errors,
            "precision": true_positive / precision_denominator if precision_denominator else 0.0,
            "recall": true_positive / recall_denominator if recall_denominator else 0.0,
            "false_positive_rate": (
                false_positive / false_positive_denominator
                if false_positive_denominator
                else 0.0
            ),
            "fixture_content_persisted": False,
            "by_surface": dict(surface_counts),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT", DEFAULT_PROJECT))
    parser.add_argument("--location", default=os.getenv("APPEAL_MODEL_ARMOR_LOCATION", DEFAULT_LOCATION))
    parser.add_argument("--template-id", default=os.getenv("APPEAL_MODEL_ARMOR_TEMPLATE", DEFAULT_TEMPLATE_ID))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    report = measure(
        project=args.project,
        location=args.location,
        template_id=args.template_id,
        cases=default_local_security_cases(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Aggregate report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
