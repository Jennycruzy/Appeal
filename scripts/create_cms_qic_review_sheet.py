#!/usr/bin/env python3
"""Create an editable CSV sheet with assistant proposals for CMS locked-test review.

The proposal is a starting point for a human reviewer. It is deliberately
derived only from the visible rationale and policy text; it never reads the
hidden regulator outcome and it is never treated as a gold label.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from appeal_evaluation import RationaleCategory, inspect_queue, route_for
from create_cms_qic_annotation_queues import load_object
from sample_cms_qic_benchmark import require_external


RULES: tuple[tuple[RationaleCategory, tuple[str, ...]], ...] = (
    (RationaleCategory.AT_RISK_DRUG_MANAGEMENT, ("at-risk", "at risk", "drug management program")),
    (RationaleCategory.PROCEDURAL_OR_JURISDICTIONAL, ("dismiss", "jurisdiction", "untimely", "timely filing", "representative", "withdrawn")),
    (RationaleCategory.NON_FORMULARY_EXCEPTION, ("non-formulary", "nonformulary", "not on the formulary", "not listed on the formulary", "formulary exception")),
    (RationaleCategory.TIERING_EXCEPTION, ("tiering exception", "tiered cost-sharing", "cost-sharing tier", "higher cost-sharing", "lower cost-sharing")),
    (RationaleCategory.STEP_THERAPY, ("step therapy", "step-therapy", "try and fail", "tried and failed", "fail first")),
    (RationaleCategory.QUANTITY_LIMIT, ("quantity limit", "quantity limitation", "dose limit", "days supply", "frequency limit")),
    (RationaleCategory.PRIOR_AUTHORIZATION, ("prior authorization", "prior-authorization", "preauthorization", "pre-authorization", "prior auth")),
    (RationaleCategory.MEDICALLY_ACCEPTED_INDICATION, ("medically accepted indication", "medically-accepted indication", "off-label", "compendia", "fda-approved indication")),
    (RationaleCategory.PAYMENT_OR_COST_SHARING, ("reimbursement", "reimburse", "payment", "copay", "co-pay", "coinsurance", "out-of-pocket")),
)


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("queue contains a non-object row")
    return rows


def sentence_span(text: str, cues: tuple[str, ...]) -> tuple[int, int] | None:
    for match in re.finditer(r"[^.!?]+(?:[.!?]+|$)", text):
        if any(cue in match.group(0).casefold() for cue in cues):
            return match.start(), match.end()
    return None


def _matches(text: str) -> list[tuple[int, int, RationaleCategory, str]]:
    normalized = text.casefold()
    matches: list[tuple[int, int, RationaleCategory, str]] = []
    for category, cues in RULES:
        for cue in cues:
            position = normalized.find(cue)
            if position >= 0:
                # Earlier, longer explicit language is a better proposal
                # signal than a generic cue appearing later in the passage.
                matches.append((position, -len(cue), category, cue))
    return matches


def classify(rationale: str, policy: str) -> tuple[RationaleCategory, tuple[str, ...], int, str, str]:
    # The decision rationale states the principal issue. Policy text is used
    # only when the rationale does not contain a usable issue cue; this avoids
    # generic policy boilerplate such as “formulary exception” overriding a
    # more specific case rationale such as tiering or step therapy.
    for source_name, text in (("decision_rationale", rationale), ("policy_context", policy)):
        matches = _matches(text)
        if not matches:
            continue
        matches.sort(key=lambda item: (item[0], item[1], item[2].value))
        category = matches[0][2]
        category_cues = tuple(sorted({cue for _, _, matched_category, cue in matches if matched_category is category}))
        competing_categories = {matched_category for _, _, matched_category, _ in matches}
        confidence = 4 if len(competing_categories) == 1 else 3
        basis = f"{source_name}: " + ", ".join(category_cues)
        return category, category_cues, confidence, source_name, basis
    return RationaleCategory.INSUFFICIENT_INFORMATION, (), 2, "", "no supported issue cue; human should consider abstention"


def span_value(row: dict[str, Any], field: str, cues: tuple[str, ...]) -> str:
    text = row["context"].get(field, "")
    if not isinstance(text, str):
        return ""
    span = sentence_span(text, cues)
    return "" if span is None else f"{span[0]}:{span[1]}"


def proposal(row: dict[str, Any]) -> dict[str, str]:
    rationale = row["context"].get("decision_rationale", "")
    policy = row["context"].get("policy_context", "")
    rationale = rationale if isinstance(rationale, str) else ""
    policy = policy if isinstance(policy, str) else ""
    category, cues, confidence, signal_source, basis = classify(rationale, policy)
    disposition = "abstained" if category is RationaleCategory.INSUFFICIENT_INFORMATION else "annotated"
    return {
        "disposition": disposition,
        "primary_category": category.value,
        "secondary_categories": "",
        "route": route_for(category).value,
        "rationale_spans": "" if disposition == "abstained" else span_value(row, "decision_rationale", cues),
        "policy_spans": "" if disposition == "abstained" else span_value(row, "policy_context", cues),
        "confidence": str(confidence),
        "signal_source": signal_source,
        "basis": basis,
    }


def create_sheet(queue_path: Path, manifest_path: Path, taxonomy_path: Path, output: Path) -> dict[str, object]:
    queue_path = require_external(queue_path, "annotation queue")
    output = require_external(output, "review sheet")
    if output.exists():
        raise FileExistsError("review sheet already exists")
    manifest = load_object(manifest_path, "annotation queue manifest")
    taxonomy = load_object(taxonomy_path, "annotation taxonomy")
    taxonomy_id = taxonomy.get("taxonomy_id")
    expected = manifest.get("queues")
    if not isinstance(taxonomy_id, str) or not isinstance(expected, dict) or not isinstance(expected.get("reviewer_a"), dict):
        raise ValueError("taxonomy or queue manifest is incomplete")
    inspection = inspect_queue(
        queue_path,
        taxonomy_version=taxonomy_id,
        annotator_id="proposal-engine",
        annotator_role="researcher",
        require_locked_test=False,
    )
    expected_a = expected["reviewer_a"]
    if inspection.order_fingerprint != expected_a.get("order_fingerprint") or inspection.context_fingerprint != expected_a.get("context_fingerprint"):
        raise ValueError("queue identity does not match the committed manifest")
    rows = [row for row in read_rows(queue_path) if row.get("split") == "locked_test"]
    if len(rows) != 100:
        raise ValueError(f"expected 100 locked-test rows, found {len(rows)}")
    columns = [
        "case_ref", "split", "part", "appeal_type", "condition", "requested_item_or_drug",
        "decision_rationale", "policy_context", "rationale_source_sha256", "policy_source_sha256",
        "assistant_proposal_disposition", "assistant_proposal_primary_category", "assistant_proposal_route",
        "assistant_proposal_rationale_spans", "assistant_proposal_policy_spans", "assistant_proposal_confidence",
        "assistant_proposal_basis", "disposition", "primary_category", "secondary_categories", "route",
        "rationale_spans", "policy_spans", "confidence", "human_reviewed", "review_note", "proposal_source",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            context = row["context"]
            source_hashes = row["source_hashes"]
            proposed = proposal(row)
            writer.writerow({
                "case_ref": row["case_ref"],
                "split": row["split"],
                "part": context.get("part", ""),
                "appeal_type": context.get("appeal_type", ""),
                "condition": context.get("condition", ""),
                "requested_item_or_drug": context.get("requested_item_or_drug", ""),
                "decision_rationale": context.get("decision_rationale", ""),
                "policy_context": context.get("policy_context", ""),
                "rationale_source_sha256": source_hashes.get("decision_rationale", ""),
                "policy_source_sha256": source_hashes.get("policy_context", ""),
                "assistant_proposal_disposition": proposed["disposition"],
                "assistant_proposal_primary_category": proposed["primary_category"],
                "assistant_proposal_route": proposed["route"],
                "assistant_proposal_rationale_spans": proposed["rationale_spans"],
                "assistant_proposal_policy_spans": proposed["policy_spans"],
                "assistant_proposal_confidence": proposed["confidence"],
                "assistant_proposal_basis": proposed["basis"],
                "disposition": proposed["disposition"],
                "primary_category": proposed["primary_category"],
                "secondary_categories": proposed["secondary_categories"],
                "route": proposed["route"],
                "rationale_spans": proposed["rationale_spans"],
                "policy_spans": proposed["policy_spans"],
                "confidence": proposed["confidence"],
                "human_reviewed": "FALSE",
                "review_note": "",
                "proposal_source": "appeal-rationale-cue-review-v2",
            })
    return {
        "status": "cms_qic_human_review_sheet_ready",
        "queue_sha256": inspection.sha256,
        "sheet_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "locked_test_rows": len(rows),
        "outcomes_in_sheet": False,
        "proposal_requires_human_review": True,
        "editable_fields": [
            "disposition", "primary_category", "secondary_categories", "route",
            "rationale_spans", "policy_spans", "confidence", "human_reviewed", "review_note",
        ],
        "proposal_fields_are_read_only_reference": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(create_sheet(args.queue, args.manifest, args.taxonomy, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
