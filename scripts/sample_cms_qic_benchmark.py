#!/usr/bin/env python3
"""Build a deterministic, stratified CMS QIC benchmark outside the repository.

The sampler streams the pinned Part D bulk CSV, enforces its acceptance and
privacy-exclusion manifest, and writes a local-only JSONL benchmark. Outcome
labels are physically separated from model inputs in every output record.
Only aggregate counts and fingerprints are suitable for repository evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import os
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from accept_cms_qic_bulk import content_identity, occurrence_identity, selection_fingerprint
from inspect_cms_qic_bulk import row_fingerprint, sha256_file


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_HEADERS = {
    "Part",
    "Decision_Date",
    "Decision_Date_Sortable",
    "Decision",
    "Appeal_Type",
    "Condition",
    "Drug",
    "Decision_Rationale",
    "Coverage_Rules",
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def normalize(value: str) -> str:
    return " ".join(value.split())


def category(value: str) -> str:
    normalized = normalize(value).casefold()
    return normalized if normalized else "missing"


def year_bucket(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    return digits[:4] if len(digits) >= 4 else "unknown"


def completeness(row: dict[str, str]) -> str:
    rationale = bool(normalize(row["Decision_Rationale"]))
    rules = bool(normalize(row["Coverage_Rules"]))
    if rationale and rules:
        return "rationale_and_rules"
    if rationale:
        return "rationale_only"
    if rules:
        return "rules_only"
    return "neither"


def stratum(row: dict[str, str]) -> str:
    return "|".join(
        (
            category(row["Decision"]),
            category(row["Appeal_Type"]),
            year_bucket(row["Decision_Date_Sortable"]),
            completeness(row),
        )
    )


def require_external(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved
    raise ValueError(f"{label} must be outside the repository: {resolved}")


def load_manifest(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("acceptance manifest must be an object")
    acceptance = document.get("acceptance")
    if not isinstance(acceptance, dict) or acceptance.get("accepted_for_local_evaluation") is not True:
        raise ValueError("acceptance manifest does not authorize local evaluation")
    if acceptance.get("accepted_for_repository") is not False:
        raise ValueError("benchmark source rows must remain outside the repository")
    return document


def excluded_rows(manifest: dict[str, Any]) -> dict[int, str]:
    selection = manifest.get("selection")
    if not isinstance(selection, dict) or not isinstance(selection.get("excluded_rows"), list):
        raise ValueError("acceptance manifest has no excluded row selection")
    result: dict[int, str] = {}
    for item in selection["excluded_rows"]:
        if not isinstance(item, dict):
            raise ValueError("excluded row must be an object")
        row_number = item.get("csv_data_row")
        row_hash = item.get("row_sha256")
        if not isinstance(row_number, int) or not isinstance(row_hash, str):
            raise ValueError("excluded row identity is invalid")
        result[row_number] = row_hash
    if len(result) != selection.get("excluded_row_count"):
        raise ValueError("excluded row count does not match manifest")
    return result


def allocate(counts: dict[str, int], total: int) -> dict[str, int]:
    if total <= 0:
        raise ValueError("sample size must be positive")
    population = sum(counts.values())
    if total > population:
        raise ValueError("sample size exceeds accepted population")
    active = {key: count for key, count in counts.items() if count > 0}
    if len(active) > total:
        ranked = sorted(active, key=lambda key: (-active[key], key))[:total]
        return {key: 1 for key in ranked}
    allocation = {key: 1 for key in active}
    remaining = total - len(active)
    if remaining == 0:
        return allocation
    capacity = {key: count - 1 for key, count in active.items()}
    capacity_total = sum(capacity.values())
    raw = {key: remaining * capacity[key] / capacity_total for key in active}
    for key in active:
        addition = min(capacity[key], int(raw[key]))
        allocation[key] += addition
    left = total - sum(allocation.values())
    order = sorted(active, key=lambda key: (-(raw[key] - int(raw[key])), -active[key], key))
    while left:
        progressed = False
        for key in order:
            if allocation[key] < active[key]:
                allocation[key] += 1
                left -= 1
                progressed = True
                if left == 0:
                    break
        if not progressed:
            raise RuntimeError("could not allocate complete sample")
    return allocation


@dataclass(frozen=True)
class Candidate:
    rank: int
    occurrence_id: str
    row_number: int
    row_hash: str
    row: dict[str, str]


def iter_rows(path: Path) -> Iterator[tuple[int, dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or set(reader.fieldnames) != REQUIRED_HEADERS:
            raise ValueError("CMS QIC CSV headers do not match the accepted Part D schema")
        for row_number, row in enumerate(reader, start=1):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"malformed CSV row {row_number}")
            yield row_number, {key: value for key, value in row.items() if key is not None and value is not None}


def ranked(seed: str, occurrence_id: str, purpose: str = "sample") -> int:
    return int(hashlib.sha256(f"{seed}:{purpose}:{occurrence_id}".encode("utf-8")).hexdigest(), 16)


def scan_population(
    csv_path: Path,
    file_hash: str,
    exclusions: dict[int, str],
) -> tuple[Counter[str], list[str], list[str]]:
    counts: Counter[str] = Counter()
    accepted_ids: list[str] = []
    excluded_ids: list[str] = []
    for row_number, row in iter_rows(csv_path):
        row_hash = row_fingerprint(row)
        content_id = content_identity(file_hash, row_hash)
        occurrence_id = occurrence_identity(content_id, row_number)
        expected_exclusion = exclusions.get(row_number)
        if expected_exclusion is not None:
            if expected_exclusion != row_hash:
                raise ValueError(f"excluded row hash mismatch at CSV row {row_number}")
            excluded_ids.append(occurrence_id)
            continue
        accepted_ids.append(occurrence_id)
        counts[stratum(row)] += 1
    return counts, accepted_ids, excluded_ids


def select_candidates(
    csv_path: Path,
    file_hash: str,
    exclusions: dict[int, str],
    quotas: dict[str, int],
    seed: str,
) -> list[Candidate]:
    heaps: dict[str, list[tuple[int, str, Candidate]]] = defaultdict(list)
    for row_number, row in iter_rows(csv_path):
        if row_number in exclusions:
            continue
        row_hash = row_fingerprint(row)
        content_id = content_identity(file_hash, row_hash)
        occurrence_id = occurrence_identity(content_id, row_number)
        key = stratum(row)
        quota = quotas.get(key, 0)
        if quota == 0:
            continue
        rank = ranked(seed, occurrence_id)
        candidate = Candidate(rank, occurrence_id, row_number, row_hash, row)
        entry = (-rank, occurrence_id, candidate)
        heap = heaps[key]
        if len(heap) < quota:
            heapq.heappush(heap, entry)
        elif entry > heap[0]:
            heapq.heapreplace(heap, entry)
    selected = [entry[2] for heap in heaps.values() for entry in heap]
    if len(selected) != sum(quotas.values()):
        raise RuntimeError("selected sample does not satisfy allocated quotas")
    return sorted(selected, key=lambda item: (stratum(item.row), item.rank, item.occurrence_id))


def split_candidates(selected: list[Candidate], locked_size: int, seed: str) -> dict[str, str]:
    selected_counts = Counter(stratum(item.row) for item in selected)
    locked_quotas = allocate(dict(selected_counts), locked_size)
    grouped: dict[str, list[Candidate]] = defaultdict(list)
    for item in selected:
        grouped[stratum(item.row)].append(item)
    assignments: dict[str, str] = {}
    for key, items in grouped.items():
        ordered = sorted(items, key=lambda item: (ranked(seed, item.occurrence_id, "split"), item.occurrence_id))
        locked = locked_quotas.get(key, 0)
        for index, item in enumerate(ordered):
            assignments[item.occurrence_id] = "locked_test" if index < locked else "development"
    return assignments


def record(candidate: Candidate, split: str) -> dict[str, object]:
    row = candidate.row
    return {
        "schema_version": "1.0",
        "case_ref": candidate.occurrence_id,
        "source": {
            "source_id": "cms_qic_decision_summaries",
            "source_class": "regulator_summary",
            "source_dataset": "part_d",
            "source_row_sha256": candidate.row_hash,
            "occurrence_identity_sha256": candidate.occurrence_id,
        },
        "split": split,
        "model_input": {
            "part": normalize(row["Part"]),
            "decision_date": normalize(row["Decision_Date"]),
            "appeal_type": normalize(row["Appeal_Type"]) or None,
            "condition": normalize(row["Condition"]) or None,
            "requested_item_or_drug": normalize(row["Drug"]) or None,
            "decision_rationale": normalize(row["Decision_Rationale"]) or None,
            "policy_context": normalize(row["Coverage_Rules"]) or None,
        },
        "hidden_labels": {
            "regulator_outcome": normalize(row["Decision"]),
            "appeal_type": normalize(row["Appeal_Type"]) or None,
            "requested_item_class": "drug",
        },
        "unsupported_labels": {
            "denial_reason": None,
            "clinical_evidence": None,
            "original_policy_version": None,
            "prior_authorization": None,
        },
    }


def build(
    csv_path: Path,
    manifest_path: Path,
    output: Path,
    *,
    sample_size: int,
    locked_size: int,
    seed: str,
) -> dict[str, object]:
    csv_path = require_external(csv_path, "CMS QIC CSV")
    output = require_external(output, "CMS QIC benchmark output")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite benchmark output: {output}")
    if locked_size <= 0 or locked_size >= sample_size:
        raise ValueError("locked size must be positive and smaller than sample size")
    if not seed.strip():
        raise ValueError("seed must not be empty")
    manifest = load_manifest(manifest_path)
    source = manifest.get("source")
    selection = manifest.get("selection")
    acceptance = manifest.get("acceptance")
    if not isinstance(source, dict) or not isinstance(selection, dict) or not isinstance(acceptance, dict):
        raise ValueError("acceptance manifest is incomplete")
    file_hash = sha256_file(csv_path)
    if file_hash != source.get("sha256"):
        raise ValueError("CMS QIC CSV hash does not match acceptance manifest")
    exclusions = excluded_rows(manifest)
    counts, accepted_ids, excluded_ids = scan_population(csv_path, file_hash, exclusions)
    if len(accepted_ids) != acceptance.get("accepted_record_count"):
        raise ValueError("accepted population count does not match manifest")
    if selection_fingerprint(accepted_ids) != selection.get("accepted_occurrence_selection_fingerprint_sha256"):
        raise ValueError("accepted occurrence fingerprint does not match manifest")
    if selection_fingerprint(excluded_ids) != selection.get("excluded_occurrence_selection_fingerprint_sha256"):
        raise ValueError("excluded occurrence fingerprint does not match manifest")
    quotas = allocate(dict(counts), sample_size)
    selected = select_candidates(csv_path, file_hash, exclusions, quotas, seed)
    assignments = split_candidates(selected, locked_size, seed)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, prefix=f".{output.name}.", suffix=".partial", delete=False) as handle:
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
    selected_strata = Counter(stratum(item.row) for item in selected)
    return {
        "schema_version": "1.0",
        "status": "cms_qic_benchmark_sample_ready",
        "recorded_at": now_iso(),
        "source": {
            "source_id": "cms_qic_decision_summaries",
            "source_class": "regulator_summary",
            "part": "part_d",
            "file_sha256": file_hash,
            "accepted_population": len(accepted_ids),
            "excluded_population": len(excluded_ids),
            "narratives_committed": False,
        },
        "sampling": {
            "algorithm": "two_pass_proportional_stratified_minimum_one_then_sha256_rank",
            "seed_sha256": hashlib.sha256(seed.encode("utf-8")).hexdigest(),
            "stratum_fields": ["decision", "appeal_type", "decision_year", "rationale_policy_completeness"],
            "population_stratum_count": len(counts),
            "sample_size": len(selected),
            "split_counts": dict(sorted(split_counts.items())),
            "selected_stratum_counts": dict(sorted(selected_strata.items())),
            "sample_identity_sha256": selection_fingerprint(sorted(item.occurrence_id for item in selected)),
        },
        "artifact": {
            "file_name": output.name,
            "sha256": sha256_file(output),
            "location": "outside_repository_only",
            "contains_narrative": True,
            "outcome_hidden_from_model_input": True,
        },
        "claim_boundary": {
            "complete_denial_package": False,
            "clinical_ground_truth": False,
            "supported_evaluation": "real_world_regulator_summary_routing_and_grounding",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=300)
    parser.add_argument("--locked-size", type=int, default=100)
    parser.add_argument("--seed", default="appeal-cms-qic-benchmark-v1")
    args = parser.parse_args()
    report = build(args.csv, args.acceptance, args.output, sample_size=args.sample_size, locked_size=args.locked_size, seed=args.seed)
    manifest_output = args.manifest_output.expanduser().resolve()
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "manifest": str(manifest_output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
