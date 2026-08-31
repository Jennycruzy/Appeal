#!/usr/bin/env python3
"""Build a privacy-screened, human-labelable CMS legal-ground benchmark.

This is intentionally separate from the CMS outcome benchmark. The explicit
CMS decision remains the outcome target; the legal-ground target is created
only by direct human review of the operative holding. The sampler filters the
accepted source population before sampling, so an empty rationale or a
technical privacy candidate cannot enter the locked set by chance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from accept_cms_qic_bulk import content_identity, occurrence_identity, selection_fingerprint
from inspect_cms_qic import privacy_categories
from inspect_cms_qic_bulk import row_fingerprint, sha256_file
from sample_cms_qic_benchmark import (
    allocate,
    excluded_rows,
    iter_rows,
    load_manifest,
    ranked,
    record,
    require_external,
    stratum,
)


def normalize(value: str) -> str:
    return " ".join(value.split())


def rationale_length_bucket(value: str) -> str:
    length = len(normalize(value))
    if length < 500:
        return "short"
    if length < 1500:
        return "medium"
    return "long"


def legal_stratum(row: dict[str, str]) -> str:
    return f"{stratum(row)}|{rationale_length_bucket(row['Decision_Rationale'])}"


def screen_row(row: dict[str, str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    reasons: list[str] = []
    if not normalize(row["Decision_Rationale"]):
        reasons.append("empty_rationale")
    if not normalize(row["Coverage_Rules"]):
        reasons.append("empty_policy_context")

    privacy: set[str] = set()
    for value in row.values():
        privacy.update(privacy_categories(value))
    if privacy:
        reasons.append("privacy_blocked")
    return tuple(sorted(set(reasons))), tuple(sorted(privacy))


@dataclass(frozen=True)
class LegalCandidate:
    rank: int
    occurrence_id: str
    row_number: int
    row_hash: str
    policy_hash: str
    row: dict[str, str]


def scan_eligible_population(
    csv_path: Path,
    file_hash: str,
    exclusions: dict[int, str],
) -> tuple[dict[str, int], list[str], Counter[str], Counter[str], Counter[str], int]:
    counts: Counter[str] = Counter()
    eligible_ids: list[str] = []
    screened_out: Counter[str] = Counter()
    privacy_candidates: Counter[str] = Counter()
    policy_hashes: Counter[str] = Counter()
    accepted_count = 0
    for row_number, row in iter_rows(csv_path):
        row_hash = row_fingerprint(row)
        expected_exclusion = exclusions.get(row_number)
        if expected_exclusion is not None:
            if expected_exclusion != row_hash:
                raise ValueError(f"excluded row hash mismatch at CSV row {row_number}")
            continue
        accepted_count += 1
        reasons, privacy = screen_row(row)
        for reason in reasons:
            screened_out[reason] += 1
        for category in privacy:
            privacy_candidates[category] += 1
        if reasons:
            continue
        occurrence_id = occurrence_identity(content_identity(file_hash, row_hash), row_number)
        eligible_ids.append(occurrence_id)
        counts[legal_stratum(row)] += 1
        policy_hashes[hashlib.sha256(normalize(row["Coverage_Rules"]).encode("utf-8")).hexdigest()] += 1
    return dict(counts), eligible_ids, screened_out, privacy_candidates, policy_hashes, accepted_count


def select_candidates(
    csv_path: Path,
    file_hash: str,
    exclusions: dict[int, str],
    quotas: dict[str, int],
    seed: str,
    policy_repeat_cap: int,
) -> list[LegalCandidate]:
    grouped: dict[str, list[LegalCandidate]] = defaultdict(list)
    for row_number, row in iter_rows(csv_path):
        if row_number in exclusions:
            continue
        reasons, _ = screen_row(row)
        if reasons:
            continue
        key = legal_stratum(row)
        quota = quotas.get(key, 0)
        if quota == 0:
            continue
        row_hash = row_fingerprint(row)
        occurrence_id = occurrence_identity(content_identity(file_hash, row_hash), row_number)
        policy_hash = hashlib.sha256(normalize(row["Coverage_Rules"]).encode("utf-8")).hexdigest()
        grouped[key].append(
            LegalCandidate(
                rank=ranked(seed, occurrence_id, "legal-ground-sample"),
                occurrence_id=occurrence_id,
                row_number=row_number,
                row_hash=row_hash,
                policy_hash=policy_hash,
                row=row,
            )
        )

    selected: list[LegalCandidate] = []
    policy_counts: Counter[str] = Counter()
    selected_by_stratum: Counter[str] = Counter()
    for key in sorted(grouped):
        ordered = sorted(grouped[key], key=lambda item: (item.rank, item.occurrence_id))
        quota = quotas[key]
        for candidate in ordered:
            if selected_by_stratum[key] >= quota:
                break
            if policy_counts[candidate.policy_hash] < policy_repeat_cap:
                selected.append(candidate)
                selected_by_stratum[key] += 1
                policy_counts[candidate.policy_hash] += 1
        if selected_by_stratum[key] < quota:
            for candidate in ordered:
                if selected_by_stratum[key] >= quota:
                    break
                if candidate not in selected:
                    selected.append(candidate)
                    selected_by_stratum[key] += 1
                    policy_counts[candidate.policy_hash] += 1

    if len(selected) != sum(quotas.values()):
        raise RuntimeError("eligible population could not satisfy the legal benchmark quotas")
    return sorted(selected, key=lambda item: (legal_stratum(item.row), item.rank, item.occurrence_id))


def split_candidates(selected: list[LegalCandidate], locked_size: int, seed: str) -> dict[str, str]:
    selected_counts = Counter(legal_stratum(item.row) for item in selected)
    locked_quotas = allocate(dict(selected_counts), locked_size)
    grouped: dict[str, list[LegalCandidate]] = defaultdict(list)
    for item in selected:
        grouped[legal_stratum(item.row)].append(item)
    assignments: dict[str, str] = {}
    for key, items in grouped.items():
        ordered = sorted(
            items,
            key=lambda item: (ranked(seed, item.occurrence_id, "legal-ground-split"), item.occurrence_id),
        )
        for index, item in enumerate(ordered):
            assignments[item.occurrence_id] = "locked_test" if index < locked_quotas.get(key, 0) else "development"
    return assignments


def build(
    csv_path: Path,
    acceptance_path: Path,
    output: Path,
    manifest_output: Path,
    *,
    sample_size: int,
    locked_size: int,
    seed: str,
    policy_repeat_cap: int,
) -> dict[str, object]:
    csv_path = require_external(csv_path, "CMS QIC CSV")
    output = require_external(output, "CMS legal-ground benchmark output")
    if output.exists() or manifest_output.exists():
        raise FileExistsError("refusing to overwrite the legal-ground benchmark or manifest")
    if sample_size <= 0 or locked_size <= 0 or locked_size >= sample_size:
        raise ValueError("sample_size must be positive and locked_size must be smaller")
    if policy_repeat_cap <= 0:
        raise ValueError("policy_repeat_cap must be positive")
    if not seed.strip():
        raise ValueError("seed must not be empty")

    manifest = load_manifest(acceptance_path)
    source = manifest.get("source")
    if not isinstance(source, dict):
        raise ValueError("acceptance manifest source is incomplete")
    file_hash = sha256_file(csv_path)
    if file_hash != source.get("sha256"):
        raise ValueError("CMS QIC CSV hash does not match acceptance manifest")
    exclusions = excluded_rows(manifest)
    counts, eligible_ids, screened_out, privacy_candidates, eligible_policy_hashes, accepted_count = scan_eligible_population(
        csv_path, file_hash, exclusions
    )
    acceptance = manifest.get("acceptance")
    if not isinstance(acceptance, dict) or accepted_count != acceptance.get("accepted_record_count"):
        raise ValueError("accepted population count does not match manifest")
    quotas = allocate(counts, sample_size)
    selected = select_candidates(csv_path, file_hash, exclusions, quotas, seed, policy_repeat_cap)
    assignments = split_candidates(selected, locked_size, seed)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=output.parent, prefix=f".{output.name}.", suffix=".partial", delete=False
        ) as handle:
            temporary = Path(handle.name)
            for candidate in sorted(selected, key=lambda item: item.occurrence_id):
                handle.write(json.dumps(record(candidate, assignments[candidate.occurrence_id]), ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    split_counts = Counter(assignments.values())
    selected_policy_hashes = Counter(item.policy_hash for item in selected)
    report: dict[str, object] = {
        "schema_version": "2.0",
        "status": "cms_qic_legal_ground_benchmark_sample_ready",
        "source": {
            "source_id": "cms_qic_decision_summaries",
            "source_class": "regulator_summary",
            "part": "part_d",
            "file_sha256": file_hash,
            "accepted_population": accepted_count,
            "source_manifest_exclusions": len(exclusions),
            "narratives_committed": False,
        },
        "screening": {
            "eligible_population": len(eligible_ids),
            "screened_out_by_reason": dict(sorted(screened_out.items())),
            "privacy_candidate_counts": dict(sorted(privacy_candidates.items())),
            "privacy_blocked_before_sampling": screened_out.get("privacy_blocked", 0),
            "empty_rationale_excluded_before_sampling": screened_out.get("empty_rationale", 0),
            "empty_policy_context_excluded_before_sampling": screened_out.get("empty_policy_context", 0),
            "eligible_population_fingerprint": selection_fingerprint(sorted(eligible_ids)),
            "privacy_detector": "technical_patterns_plus_person_name_context",
            "raw_values_in_report": False,
        },
        "sampling": {
            "algorithm": "screen_then_proportional_stratified_minimum_one_then_policy_diversity_rank",
            "seed_sha256": hashlib.sha256(seed.encode("utf-8")).hexdigest(),
            "stratum_fields": ["decision", "appeal_type", "decision_year", "rationale_policy_completeness", "rationale_length_bucket"],
            "population_stratum_count": len(counts),
            "sample_size": len(selected),
            "locked_test_size": locked_size,
            "split_counts": dict(sorted(split_counts.items())),
            "sample_identity_sha256": selection_fingerprint(sorted(item.occurrence_id for item in selected)),
            "eligible_policy_context_unique_count": len(eligible_policy_hashes),
            "selected_policy_context_unique_count": len(selected_policy_hashes),
            "policy_context_repeat_cap_preference": policy_repeat_cap,
            "selected_policy_context_repeat_counts": {
                key: count for key, count in sorted(selected_policy_hashes.items()) if count > 1
            },
        },
        "tracks": {
            "regulator_outcome": {
                "gold_source": "hidden_labels.regulator_outcome",
                "source_field": "Decision",
                "label_status": "explicit_CMS_field",
                "reviewer_required": False,
            },
            "legal_ground": {
                "gold_source": "two_direct_human_reviews_of_operative_holdings",
                "source_fields": ["decision_rationale", "policy_context"],
                "label_status": "pending_direct_human_review",
                "reviewer_required": True,
                "assistant_prefill_allowed": False,
            },
        },
        "artifact": {
            "file_name": output.name,
            "sha256": sha256_file(output),
            "location": "outside_repository_only",
            "contains_narrative": True,
            "outcome_hidden_from_annotation_input": True,
        },
        "claim_boundary": {
            "complete_denial_package": False,
            "clinical_ground_truth": False,
            "regulator_outcome_track": True,
            "legal_ground_track": "requires_two_direct_human_reviews_and_adjudication",
            "full_appeal_evaluation": False,
        },
    }
    manifest_output = manifest_output.expanduser().resolve()
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=150)
    parser.add_argument("--locked-size", type=int, default=50)
    parser.add_argument("--seed", default="appeal-cms-qic-legal-ground-v2")
    parser.add_argument("--policy-repeat-cap", type=int, default=2)
    args = parser.parse_args()
    report = build(
        args.csv,
        args.acceptance,
        args.output,
        args.manifest_output,
        sample_size=args.sample_size,
        locked_size=args.locked_size,
        seed=args.seed,
        policy_repeat_cap=args.policy_repeat_cap,
    )
    print(json.dumps({"status": report["status"], "manifest": str(args.manifest_output.expanduser().resolve())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
