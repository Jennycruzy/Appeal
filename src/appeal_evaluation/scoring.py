"""Deterministic, source-aware metrics for Appeal predictions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from .contracts import AppealCasePackage, AppealPrediction, EvaluationTask, SourceCapabilities


@dataclass(frozen=True)
class MetricResult:
    task: EvaluationTask
    metric: str
    value: float
    numerator: int
    denominator: int
    abstentions: int
    confidence_low: float | None = None
    confidence_high: float | None = None


@dataclass(frozen=True)
class EvaluationReport:
    schema_version: str
    source_id: str
    case_count: int
    prediction_count: int
    metrics: tuple[MetricResult, ...]


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        raise ValueError("total must be positive")
    if successes < 0 or successes > total:
        raise ValueError("successes must be between zero and total")
    probability = successes / total
    denominator = 1 + z * z / total
    centre = (probability + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((probability * (1 - probability) + z * z / (4 * total)) / total) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def _scalar_metric(
    task: EvaluationTask,
    cases: tuple[AppealCasePackage, ...],
    predictions: dict[str, AppealPrediction],
    gold: Callable[[AppealCasePackage], str | None],
    predicted: Callable[[AppealPrediction], str | None],
) -> MetricResult:
    correct = 0
    denominator = 0
    abstentions = 0
    for case in cases:
        if task not in case.allowed_tasks:
            continue
        expected = gold(case)
        if expected is None:
            raise ValueError(f"case {case.case_ref} supports {task.value} but has no gold label")
        prediction = predictions[case.case_ref]
        value = predicted(prediction)
        if task in prediction.abstained_tasks or value is None:
            abstentions += 1
            continue
        denominator += 1
        if value == expected:
            correct += 1
    if denominator == 0:
        return MetricResult(task, "selective_accuracy", 0.0, 0, 0, abstentions)
    low, high = wilson_interval(correct, denominator)
    return MetricResult(task, "selective_accuracy", correct / denominator, correct, denominator, abstentions, low, high)


def _set_metric(
    task: EvaluationTask,
    cases: tuple[AppealCasePackage, ...],
    predictions: dict[str, AppealPrediction],
    gold: Callable[[AppealCasePackage], tuple[str, ...]],
    predicted: Callable[[AppealPrediction], tuple[str, ...]],
) -> tuple[MetricResult, MetricResult, MetricResult]:
    true_positive = 0
    predicted_total = 0
    gold_total = 0
    abstentions = 0
    for case in cases:
        if task not in case.allowed_tasks:
            continue
        prediction = predictions[case.case_ref]
        if task in prediction.abstained_tasks:
            abstentions += 1
            continue
        expected = set(gold(case))
        observed = set(predicted(prediction))
        true_positive += len(expected & observed)
        predicted_total += len(observed)
        gold_total += len(expected)
    precision = true_positive / predicted_total if predicted_total else 0.0
    recall = true_positive / gold_total if gold_total else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return (
        MetricResult(task, "micro_precision", precision, true_positive, predicted_total, abstentions),
        MetricResult(task, "micro_recall", recall, true_positive, gold_total, abstentions),
        MetricResult(task, "micro_f1", f1, 0, 0, abstentions),
    )


def evaluate_predictions(
    capabilities: SourceCapabilities,
    cases: tuple[AppealCasePackage, ...],
    predictions: tuple[AppealPrediction, ...],
) -> EvaluationReport:
    if not cases:
        raise ValueError("at least one case is required")
    for case in cases:
        case.require_compatible(capabilities)
    prediction_index = {prediction.case_ref: prediction for prediction in predictions}
    if len(prediction_index) != len(predictions):
        raise ValueError("predictions must have unique case_ref values")
    case_refs = {case.case_ref for case in cases}
    if set(prediction_index) != case_refs:
        missing = sorted(case_refs - set(prediction_index))
        extra = sorted(set(prediction_index) - case_refs)
        raise ValueError(f"prediction coverage mismatch: missing={missing}, extra={extra}")

    metrics: list[MetricResult] = []
    scalar_specs: tuple[tuple[EvaluationTask, Callable[[AppealCasePackage], str | None], Callable[[AppealPrediction], str | None]], ...] = (
        (EvaluationTask.APPEAL_TYPE, lambda case: case.appeal_type, lambda item: item.appeal_type),
        (EvaluationTask.REQUESTED_ITEM_CLASS, lambda case: case.requested_item_class, lambda item: item.requested_item_class),
        (EvaluationTask.DENIAL_REASON, lambda case: case.denial_reason, lambda item: item.denial_reason),
        (EvaluationTask.ROUTE, lambda case: case.route, lambda item: item.route),
        (EvaluationTask.REGULATOR_OUTCOME, lambda case: case.regulator_outcome, lambda item: item.regulator_outcome),
    )
    for task, scalar_gold, scalar_predicted in scalar_specs:
        if task in capabilities.supported_tasks:
            metrics.append(_scalar_metric(task, cases, prediction_index, scalar_gold, scalar_predicted))

    set_specs: tuple[tuple[EvaluationTask, Callable[[AppealCasePackage], tuple[str, ...]], Callable[[AppealPrediction], tuple[str, ...]]], ...] = (
        (EvaluationTask.COVERAGE_RULES, lambda case: case.coverage_rule_ids, lambda item: item.coverage_rule_ids),
        (EvaluationTask.POLICY_CRITERIA, lambda case: case.policy_criterion_ids, lambda item: item.policy_criterion_ids),
        (EvaluationTask.EVIDENCE_SELECTION, lambda case: tuple(label.evidence_ref for label in case.evidence_labels), lambda item: item.evidence_refs),
        (EvaluationTask.MISSING_EVIDENCE, lambda case: case.missing_evidence_ids, lambda item: item.missing_evidence_ids),
        (EvaluationTask.CLAIM_SUPPORT, lambda case: case.supported_claim_ids, lambda item: item.supported_claim_ids),
    )
    for task, set_gold, set_predicted in set_specs:
        if task in capabilities.supported_tasks:
            metrics.extend(_set_metric(task, cases, prediction_index, set_gold, set_predicted))

    return EvaluationReport("1.0", capabilities.source_id, len(cases), len(predictions), tuple(metrics))
