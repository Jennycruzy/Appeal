#!/usr/bin/env python3
"""Create a conservative, metadata-only CMS QIC privacy-review proposal.

This is a triage aid, not a legal clearance. It resolves candidate values from
the unchanged local CSV but writes only hashes, match categories, generic
decision bases, and reviewer metadata to an output outside the repository.
Every proposal remains pending user verification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from inspect_cms_qic import ADDRESS, privacy_categories
from review_cms_qic_bulk_privacy import (
    candidate_groups,
    load_candidate_values,
    load_json,
    require_external,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[1]
MEMBER_VALUE = re.compile(
    r"member\s*(?:id|number|no\.?|#)\s*(?:is|was|:|-)?\s*"
    r"([A-Z0-9][A-Z0-9-]{3,})",
    re.I,
)
DOB_VALUE = re.compile(
    r"(?:date\s+of\s+birth|\bDOB\b)\s*(?:is|was|:|-)?\s*"
    r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:,|\s)\s*\d{4})",
    re.I,
)
MEASUREMENT_WORDS = frozenset(
    {
        "capsule",
        "capsules",
        "daily",
        "day",
        "days",
        "dose",
        "doses",
        "g",
        "gram",
        "grams",
        "hour",
        "hours",
        "mcg",
        "mg",
        "milligram",
        "milligrams",
        "ml",
        "month",
        "months",
        "per",
        "tablet",
        "tablets",
        "unit",
        "units",
        "week",
        "weeks",
    }
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def recommendation(value: str, match_types: list[str]) -> tuple[str, str]:
    categories = set(privacy_categories(value))
    if "ssn_shape" in categories:
        return "b", "direct_ssn_shape_requires_block"
    if "email_shape" in categories:
        return "l", "email_shape_requires_context_review"
    if "phone_shape" in categories:
        return "l", "phone_shape_requires_context_review"
    member_match = MEMBER_VALUE.search(value)
    if "member_id_label" in categories and member_match is not None:
        if any(character.isdigit() for character in member_match.group(1)):
            return "b", "member_id_with_value_shape_requires_block"
        return "f", "member_id_label_without_value_shape"
    if "date_of_birth_label" in categories and DOB_VALUE.search(value):
        return "b", "date_of_birth_with_date_shape_requires_block"
    if "physical_address_shape" in categories:
        address_match = ADDRESS.search(value)
        if address_match is not None:
            words = {word.casefold() for word in re.findall(r"[A-Za-z]+", address_match.group(0))}
            if words.intersection(MEASUREMENT_WORDS):
                return "f", "address_pattern_in_measurement_or_dosage_context"
        return "l", "physical_address_shape_requires_context_review"
    if "member_id_label" in categories:
        return "f", "member_id_label_without_value_shape"
    if "date_of_birth_label" in categories:
        return "f", "date_of_birth_label_without_date_shape"
    return "f", "technical_pattern_not_confirmed_as_identifier"


def write_proposal(
    output: Path,
    *,
    source: dict[str, Any],
    reviewer: str,
    candidates: list[dict[str, Any]],
    proposals: dict[str, tuple[str, str]],
    replace: bool = False,
) -> None:
    if output.exists() and not replace:
        raise FileExistsError(f"refusing to overwrite CMS QIC privacy proposal: {output}")
    counts: Counter[str] = Counter(decision for decision, _ in proposals.values())
    report = {
        "schema_version": "0.1",
        "status": "agent_proposed_pending_user_verification",
        "source": source,
        "privacy_review": {
            "reviewer": reviewer,
            "reviewed_at": now_iso(),
            "review_method": "conservative_agent_technical_triage",
            "user_verification_required": True,
            "candidate_record_count": len(candidates),
            "decision_count": len(proposals),
            "unresolved_count": len(candidates) - len(proposals),
            "decision_counts": dict(sorted(counts.items())),
            "raw_values_in_decision_file": False,
            "decisions": [
                {
                    "value_sha256": str(candidate["value_sha256"]),
                    "decision": proposals[str(candidate["value_sha256"])][0],
                    "decision_basis": proposals[str(candidate["value_sha256"])][1],
                    "match_types": candidate["match_types"],
                    "fields": candidate["fields"],
                    "occurrence_count": candidate["occurrence_count"],
                }
                for candidate in candidates
            ],
        },
    }
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
            handle.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
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
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviewer", default="assistant-delegated-by-user")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    csv_path = require_external(args.csv, "CMS QIC bulk CSV")
    report_path = args.report.expanduser().resolve()
    output = require_external(args.output, "CMS QIC privacy proposal output")
    if not csv_path.is_file():
        raise FileNotFoundError(f"CMS QIC bulk CSV does not exist: {csv_path}")
    if not report_path.is_file():
        raise FileNotFoundError(f"CMS QIC bulk report does not exist: {report_path}")

    report = load_json(report_path)
    artifact = report.get("artifact")
    source = report.get("source")
    if not isinstance(artifact, dict) or not isinstance(source, dict):
        raise ValueError("CMS QIC bulk report is missing artifact or source metadata")
    actual_hash = sha256_file(csv_path)
    if actual_hash != artifact.get("sha256"):
        raise ValueError("CMS QIC bulk CSV hash does not match the inspection report")

    candidates = candidate_groups(report)
    values = load_candidate_values(csv_path, candidates)
    proposals = {
        str(candidate["value_sha256"]): recommendation(
            values[str(candidate["value_sha256"])], candidate["match_types"]
        )
        for candidate in candidates
    }
    write_proposal(
        output,
        source={
            "source_id": report.get("source_id"),
            "part": source.get("part"),
            "file_name": csv_path.name,
            "sha256": actual_hash,
            "inspection_report": report_path.name,
        },
        reviewer=args.reviewer.strip() or "assistant-delegated-by-user",
        candidates=candidates,
        proposals=proposals,
        replace=args.replace,
    )
    counts = Counter(decision for decision, _ in proposals.values())
    print(
        json.dumps(
            {
                "status": "agent_proposed_pending_user_verification",
                "candidate_count": len(candidates),
                "decision_counts": dict(sorted(counts.items())),
                "output": str(output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
