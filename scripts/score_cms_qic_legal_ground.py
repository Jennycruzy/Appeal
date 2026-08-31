#!/usr/bin/env python3
"""Score legal-ground predictions against the independently reviewed CMS gold.

The gold file is produced only after two direct, outcome-blinded human reviews
and adjudication of disagreements. This scorer is deliberately separate from
the official CMS outcome scorer: it evaluates operative legal grounds,
secondary issues, routes, and source spans, not the regulator's decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from appeal_evaluation import OperationalRoute, RationaleCategory, SpanRole, route_for
from inspect_cms_qic_bulk import sha256_file
from sample_cms_qic_benchmark import require_external
from score_cms_qic_outcomes import benchmark_outcomes, case_ref, read_jsonl


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_KEYS = frozenset(
    {
        "regulator_outcome",
        "hidden_labels",
        "decision_rationale",
        "policy_context",
        "raw_row",
        "source_row",
    }
)
PREDICTION_KEYS = frozenset(
    {
        "case_ref",
        "taxonomy_version",
        "disposition",
        "primary_category",
        "secondary_categories",
        "route",
        "rationale_spans",
        "policy_spans",
        "abstained",
    }
)


def contains_forbidden(value: object) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                return key
            found = contains_forbidden(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = contains_forbidden(child)
            if found is not None:
                return found
    return None


def taxonomy_id(path: Path) -> tuple[str, str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("taxonomy_id"), str):
        raise ValueError("legal-ground taxonomy has no taxonomy_id")
    return value["taxonomy_id"], sha256_file(path)


def benchmark_contexts(path: Path, manifest: Path) -> dict[str, dict[str, str]]:
    benchmark_outcomes(path, manifest)
    contexts: dict[str, dict[str, str]] = {}
    for index, row in enumerate(read_jsonl(require_external(path, "CMS legal-ground benchmark"), "benchmark"), start=1):
        if row.get("split") != "locked_test":
            continue
        reference = case_ref(row.get("case_ref"), f"benchmark row {index}.case_ref")
        model_input = row.get("model_input")
        if not isinstance(model_input, dict):
            raise ValueError(f"benchmark row {index} lacks model_input")
        contexts[reference] = {
            "decision_rationale": _source_text(model_input.get("decision_rationale"), index, "decision_rationale"),
            "policy_context": _source_text(model_input.get("policy_context"), index, "policy_context"),
        }
    return contexts


def _source_text(value: object, index: int, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"benchmark row {index}.model_input.{field} must be non-empty")
    return value


def span_signature(
    value: object,
    context: dict[str, str],
    label: str,
) -> tuple[tuple[str, int, int, str, str], ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    result: list[tuple[str, int, int, str, str]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        source_field = raw.get("source_field")
        if source_field not in {"decision_rationale", "policy_context"}:
            raise ValueError(f"{label}[{index}].source_field is unsupported")
        start = raw.get("start")
        end = raw.get("end")
        if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
            raise ValueError(f"{label}[{index}] offsets must be integers")
        source = context[source_field]
        if start < 0 or end < start or end > len(source):
            raise ValueError(f"{label}[{index}] is outside source bounds")
        source_hash = raw.get("source_sha256")
        expected_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if source_hash != expected_hash:
            raise ValueError(f"{label}[{index}].source_sha256 does not match source")
        default_role = SpanRole.OPERATIVE_HOLDING.value if source_field == "decision_rationale" else SpanRole.POLICY_CONTEXT.value
        role = raw.get("span_role", default_role)
        expected_role = default_role
        if role != expected_role:
            raise ValueError(f"{label}[{index}].span_role does not match source_field")
        result.append((source_field, start, end, source_hash, role))
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicate spans")
    return tuple(sorted(result))


def category(value: object, label: str) -> str:
    try:
        return RationaleCategory(value).value
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} is not a supported legal-ground category") from error


def secondary(value: object, primary: str, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    values = tuple(category(item, f"{label}[{index}]") for index, item in enumerate(value))
    if len(values) != len(set(values)):
        raise ValueError(f"{label} contains duplicates")
    if primary in values or RationaleCategory.INSUFFICIENT_INFORMATION.value in values:
        raise ValueError(f"{label} contains an invalid secondary category")
    return values


def disposition(value: object, label: str) -> str:
    if value not in {"annotated", "abstained"}:
        raise ValueError(f"{label} must be annotated or abstained")
    return str(value)


def label_payload(row: dict[str, Any], context: dict[str, str], label: str) -> dict[str, Any]:
    forbidden = contains_forbidden(row)
    if forbidden is not None:
        raise ValueError(f"{label} contains forbidden field {forbidden}")
    primary = category(row.get("primary_category"), f"{label}.primary_category")
    secondary_values = secondary(row.get("secondary_categories", []), primary, f"{label}.secondary_categories")
    route_value = row.get("route")
    try:
        route = OperationalRoute(route_value).value
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label}.route is unsupported") from error
    if route != route_for(RationaleCategory(primary)).value:
        raise ValueError(f"{label}.route does not match primary_category")
    disposition_value = disposition(row.get("disposition"), f"{label}.disposition")
    abstained = row.get("abstained", disposition_value == "abstained")
    if not isinstance(abstained, bool):
        raise ValueError(f"{label}.abstained must be boolean")
    if abstained != (disposition_value == "abstained"):
        raise ValueError(f"{label}.abstained disagrees with disposition")
    if abstained:
        if primary != RationaleCategory.INSUFFICIENT_INFORMATION.value:
            raise ValueError(f"{label} abstention requires insufficient_information")
        if row.get("rationale_spans", []) or row.get("policy_spans", []):
            raise ValueError(f"{label} abstention must not claim source spans")
    rationale_spans = span_signature(row.get("rationale_spans", []), context, f"{label}.rationale_spans")
    policy_spans = span_signature(row.get("policy_spans", []), context, f"{label}.policy_spans")
    if not abstained and not rationale_spans and not policy_spans:
        raise ValueError(f"{label} annotated label requires a source span")
    return {
        "disposition": disposition_value,
        "primary_category": primary,
        "secondary_categories": secondary_values,
        "route": route,
        "rationale_spans": rationale_spans,
        "policy_spans": policy_spans,
        "abstained": abstained,
    }


def load_gold(path: Path, contexts: dict[str, dict[str, str]], expected_taxonomy: str) -> tuple[dict[str, dict[str, Any]], str]:
    path = require_external(path, "CMS legal-ground gold output")
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(read_jsonl(path, "gold"), start=1):
        reference = case_ref(row.get("case_ref"), f"gold row {index}.case_ref")
        if reference in result:
            raise ValueError(f"gold repeats case_ref at row {index}")
        if row.get("taxonomy_version") != expected_taxonomy:
            raise ValueError(f"gold row {index} has the wrong taxonomy version")
        context = contexts.get(reference)
        if context is None:
            raise ValueError(f"gold row {index} is not in the locked-test benchmark")
        result[reference] = label_payload(row, context, f"gold row {index}")
    return result, sha256_file(path)


def load_predictions(path: Path, contexts: dict[str, dict[str, str]], expected_taxonomy: str, expected: set[str]) -> tuple[dict[str, dict[str, Any]], str]:
    path = require_external(path, "CMS legal-ground predictions")
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(read_jsonl(path, "prediction"), start=1):
        unknown = set(row) - PREDICTION_KEYS
        if unknown:
            raise ValueError(f"prediction row {index} contains unsupported fields: {', '.join(sorted(unknown))}")
        reference = case_ref(row.get("case_ref"), f"prediction row {index}.case_ref")
        if reference in result:
            raise ValueError(f"prediction repeats case_ref at row {index}")
        if row.get("taxonomy_version", expected_taxonomy) != expected_taxonomy:
            raise ValueError(f"prediction row {index} has the wrong taxonomy version")
        context = contexts.get(reference)
        if context is None:
            raise ValueError(f"prediction row {index} is not in the locked-test benchmark")
        result[reference] = label_payload(row, context, f"prediction row {index}")
    if set(result) != expected:
        raise ValueError("legal-ground prediction coverage does not match the human gold set")
    return result, sha256_file(path)


def binary_accuracy(gold: dict[str, dict[str, Any]], predictions: dict[str, dict[str, Any]], field: str) -> dict[str, Any]:
    correct = sum(predictions[reference][field] == value[field] for reference, value in gold.items())
    total = len(gold)
    return {"value": correct / total if total else None, "numerator": correct, "denominator": total}


def set_metrics(gold: dict[str, dict[str, Any]], predictions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    true_positive = predicted_total = gold_total = 0
    exact = 0
    for reference, value in gold.items():
        expected = {value["primary_category"], *value["secondary_categories"]}
        observed = {predictions[reference]["primary_category"], *predictions[reference]["secondary_categories"]}
        true_positive += len(expected & observed)
        predicted_total += len(observed)
        gold_total += len(expected)
        exact += expected == observed
    precision = true_positive / predicted_total if predicted_total else 0.0
    recall = true_positive / gold_total if gold_total else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "micro_precision": precision,
        "micro_recall": recall,
        "micro_f1": f1,
        "exact_issue_set_match": exact / len(gold) if gold else None,
        "true_positive": true_positive,
        "predicted_issue_count": predicted_total,
        "gold_issue_count": gold_total,
    }


def span_metric(gold: dict[str, dict[str, Any]], predictions: dict[str, dict[str, Any]], field: str) -> dict[str, Any]:
    eligible = [reference for reference, value in gold.items() if value[field]]
    matches = sum(predictions[reference][field] == gold[reference][field] for reference in eligible)
    return {
        "value": matches / len(eligible) if eligible else None,
        "matches": matches,
        "eligible_cases": len(eligible),
        "definition": "exact source_field/start/end/source_hash/span_role tuple match",
    }


def score(
    benchmark_path: Path,
    sample_manifest_path: Path,
    gold_path: Path,
    predictions_path: Path,
    taxonomy_path: Path,
    output_path: Path,
    *,
    gold_report_path: Path | None = None,
) -> dict[str, Any]:
    contexts = benchmark_contexts(benchmark_path, sample_manifest_path)
    expected_taxonomy, taxonomy_hash = taxonomy_id(taxonomy_path)
    gold, gold_hash = load_gold(gold_path, contexts, expected_taxonomy)
    if set(gold) != set(contexts):
        raise ValueError("human gold does not cover exactly the locked-test benchmark")
    predictions, prediction_hash = load_predictions(predictions_path, contexts, expected_taxonomy, set(gold))
    if gold_report_path is not None:
        report = json.loads(gold_report_path.read_text(encoding="utf-8"))
        if not isinstance(report, dict) or report.get("gold_claim_allowed") is not True:
            raise ValueError("gold report does not authorize legal-ground scoring")
        gold_artifact = report.get("gold_output")
        if not isinstance(gold_artifact, dict) or gold_artifact.get("sha256") != gold_hash:
            raise ValueError("gold output does not match its committed report")

    resolution_counts = Counter(
        row.get("resolution", "unknown") for row in read_jsonl(require_external(gold_path, "CMS legal-ground gold output"), "gold")
    )
    abstentions = sum(value["abstained"] for value in predictions.values())
    return {
        "schema_version": "1.0",
        "status": "cms_qic_legal_ground_score_ready",
        "track": {
            "name": "inferred_legal_ground",
            "gold_source": "two_direct_human_reviews_plus_adjudication",
            "taxonomy_id": expected_taxonomy,
            "official_CMS_outcome_scoring": "separate_track",
            "full_appeal_evaluation": False,
        },
        "source": {
            "benchmark_sha256": sha256_file(require_external(benchmark_path, "CMS legal-ground benchmark")),
            "sample_manifest_sha256": sha256_file(sample_manifest_path),
            "locked_test_count": len(gold),
            "taxonomy_sha256": taxonomy_hash,
            "human_gold_sha256": gold_hash,
            "human_gold_resolution_counts": dict(sorted(resolution_counts.items())),
            "narratives_in_report": False,
        },
        "prediction_artifact": {
            "sha256": prediction_hash,
            "location": "outside_repository_only",
        },
        "metrics": {
            "primary_category_accuracy": binary_accuracy(gold, predictions, "primary_category"),
            "operational_route_accuracy": binary_accuracy(gold, predictions, "route"),
            "disposition_accuracy": binary_accuracy(gold, predictions, "disposition"),
            "issue_set": set_metrics(gold, predictions),
            "operative_holding_span": span_metric(gold, predictions, "rationale_spans"),
            "policy_span_when_gold_is_present": span_metric(gold, predictions, "policy_spans"),
            "abstention_rate": {
                "value": abstentions / len(gold) if gold else None,
                "abstentions": abstentions,
                "denominator": len(gold),
            },
        },
        "distributions": {
            "gold_primary_categories": dict(sorted(Counter(value["primary_category"] for value in gold.values()).items())),
            "predicted_primary_categories": dict(sorted(Counter(value["primary_category"] for value in predictions.values()).items())),
            "gold_secondary_categories": dict(sorted(Counter(category for value in gold.values() for category in value["secondary_categories"]).items())),
        },
        "claim_boundary": {
            "official_CMS_outcome_scoring": False,
            "inferred_legal_ground_scoring": True,
            "complete_denial_package": False,
            "clinical_appropriateness": False,
            "full_appeal_evaluation": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--sample-manifest", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--gold-report", type=Path)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    try:
        output.relative_to(ROOT.resolve())
    except ValueError:
        raise ValueError(f"score report must be inside the repository: {output}") from None
    if output.exists():
        raise FileExistsError("refusing to overwrite a legal-ground score report")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = score(
        args.benchmark,
        args.sample_manifest,
        args.gold,
        args.predictions,
        args.taxonomy,
        output,
        gold_report_path=args.gold_report,
    )
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
