#!/usr/bin/env python3
"""Create independently ordered, outcome-blinded CMS annotation queues."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from inspect_cms_qic_bulk import sha256_file
from sample_cms_qic_benchmark import require_external


ROOT = Path(__file__).resolve().parents[1]


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def queue_rank(case_ref: str, queue_id: str) -> str:
    return hashlib.sha256(f"cms-qic-annotation:{queue_id}:{case_ref}".encode("utf-8")).hexdigest()


def create_queues(
    benchmark_path: Path,
    sample_manifest_path: Path,
    taxonomy_path: Path,
    queue_a: Path,
    queue_b: Path,
) -> dict[str, object]:
    benchmark_path = require_external(benchmark_path, "benchmark input")
    queue_a = require_external(queue_a, "annotation queue A")
    queue_b = require_external(queue_b, "annotation queue B")
    if queue_a == queue_b:
        raise ValueError("annotation queue paths must be different")
    if queue_a.exists() or queue_b.exists():
        raise FileExistsError("refusing to overwrite an annotation queue")
    sample_manifest = load_object(sample_manifest_path, "sample manifest")
    taxonomy = load_object(taxonomy_path, "taxonomy")
    artifact = sample_manifest.get("artifact")
    rules = taxonomy.get("annotation_rules")
    categories = taxonomy.get("categories")
    if not isinstance(artifact, dict) or sha256_file(benchmark_path) != artifact.get("sha256"):
        raise ValueError("benchmark input does not match sample manifest")
    if not isinstance(rules, dict) or rules.get("outcome_blinded") is not True:
        raise ValueError("taxonomy does not require outcome blinding")
    if not isinstance(categories, dict) or not categories:
        raise ValueError("taxonomy has no categories")

    items: list[dict[str, object]] = []
    split_counts: Counter[str] = Counter()
    with benchmark_path.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"benchmark row {index} is not an object")
            case_ref = record.get("case_ref")
            split = record.get("split")
            model_input = record.get("model_input")
            if not isinstance(case_ref, str) or not isinstance(split, str) or not isinstance(model_input, dict):
                raise ValueError(f"benchmark row {index} is incomplete")
            if "regulator_outcome" in model_input or "hidden_labels" in model_input:
                raise ValueError("annotation input contains a hidden outcome label")
            split_counts[split] += 1
            rationale = model_input.get("decision_rationale")
            policy = model_input.get("policy_context")
            rationale_text = rationale if isinstance(rationale, str) else ""
            policy_text = policy if isinstance(policy, str) else ""
            items.append(
                {
                    "case_ref": case_ref,
                    "split": split,
                    "context": {
                        "part": model_input.get("part"),
                        "appeal_type": model_input.get("appeal_type"),
                        "condition": model_input.get("condition"),
                        "requested_item_or_drug": model_input.get("requested_item_or_drug"),
                        "decision_rationale": rationale_text,
                        "policy_context": policy_text,
                    },
                    "source_hashes": {
                        "decision_rationale": hashlib.sha256(rationale_text.encode("utf-8")).hexdigest(),
                        "policy_context": hashlib.sha256(policy_text.encode("utf-8")).hexdigest(),
                    },
                    "annotation": {
                        "disposition": None,
                        "primary_category": None,
                        "secondary_categories": [],
                        "route": None,
                        "rationale_spans": [],
                        "policy_spans": [],
                        "confidence": None,
                    },
                }
            )

    queue_a.parent.mkdir(parents=True, exist_ok=True)
    queue_b.parent.mkdir(parents=True, exist_ok=True)
    for queue_id, output in (("reviewer_a", queue_a), ("reviewer_b", queue_b)):
        ordered = sorted(items, key=lambda item: queue_rank(str(item["case_ref"]), queue_id))
        with output.open("x", encoding="utf-8") as handle:
            for item in ordered:
                handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    order_a = [str(item["case_ref"]) for item in sorted(items, key=lambda item: queue_rank(str(item["case_ref"]), "reviewer_a"))]
    order_b = [str(item["case_ref"]) for item in sorted(items, key=lambda item: queue_rank(str(item["case_ref"]), "reviewer_b"))]
    return {
        "schema_version": "1.0",
        "status": "outcome_blinded_annotation_queues_ready",
        "recorded_at": now_iso(),
        "taxonomy": {
            "taxonomy_id": taxonomy.get("taxonomy_id"),
            "sha256": sha256_file(taxonomy_path),
            "category_count": len(categories),
            "official_source_count": len(taxonomy.get("official_sources", [])),
        },
        "source": {
            "benchmark_sha256": sha256_file(benchmark_path),
            "record_count": len(items),
            "split_counts": dict(sorted(split_counts.items())),
            "outcomes_in_queues": False,
            "narratives_in_repository": False,
        },
        "queues": {
            "reviewer_a": {
                "location": "outside_repository_only",
                "sha256": sha256_file(queue_a),
                "order_fingerprint": hashlib.sha256("\n".join(order_a).encode("ascii")).hexdigest(),
            },
            "reviewer_b": {
                "location": "outside_repository_only",
                "sha256": sha256_file(queue_b),
                "order_fingerprint": hashlib.sha256("\n".join(order_b).encode("ascii")).hexdigest(),
            },
            "independent_order": order_a != order_b,
        },
        "gold_policy": {
            "locked_test_independent_annotations_required": 2,
            "disagreement_requires_adjudication": True,
            "model_generated_label_can_be_gold": False,
            "gold_status": "pending_human_annotation",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--sample-manifest", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--queue-a", type=Path, required=True)
    parser.add_argument("--queue-b", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = create_queues(args.benchmark, args.sample_manifest, args.taxonomy, args.queue_a, args.queue_b)
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
