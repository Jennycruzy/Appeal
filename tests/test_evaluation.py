from __future__ import annotations

import unittest

from appeal_evaluation import (
    AppealCasePackage,
    AppealPrediction,
    EvaluationTask,
    EvidenceLabel,
    SourceCapabilities,
    SourceClass,
    evaluate_predictions,
    wilson_interval,
)


HASH = "a" * 64
MODEL_HASH = "b" * 64
POLICY_HASH = "c" * 64


def cms_capabilities() -> SourceCapabilities:
    return SourceCapabilities(
        source_id="cms_qic_decision_summaries",
        source_class=SourceClass.REGULATOR_SUMMARY,
        supported_tasks=frozenset(
            {
                EvaluationTask.APPEAL_TYPE,
                EvaluationTask.REQUESTED_ITEM_CLASS,
                EvaluationTask.COVERAGE_RULES,
                EvaluationTask.ROUTE,
                EvaluationTask.REGULATOR_OUTCOME,
            }
        ),
    )


def cms_case(case_ref: str, appeal_type: str, outcome: str) -> AppealCasePackage:
    return AppealCasePackage(
        case_ref=case_ref,
        source_id="cms_qic_decision_summaries",
        source_class=SourceClass.REGULATOR_SUMMARY,
        source_fingerprint=HASH,
        split="locked_test",
        allowed_tasks=cms_capabilities().supported_tasks,
        appeal_type=appeal_type,
        requested_item_class="drug",
        coverage_rule_ids=("rule-1", "rule-2"),
        route="external_review",
        regulator_outcome=outcome,
    )


def prediction(case_ref: str, appeal_type: str | None, outcome: str | None) -> AppealPrediction:
    return AppealPrediction(
        case_ref=case_ref,
        model_fingerprint=MODEL_HASH,
        policy_fingerprint=POLICY_HASH,
        code_revision="revision-under-test",
        appeal_type=appeal_type,
        requested_item_class="drug",
        coverage_rule_ids=("rule-1",),
        route="external_review",
        regulator_outcome=outcome,
        latency_ms=12,
    )


class EvaluationContractTests(unittest.TestCase):
    def test_regulator_summary_cannot_claim_complete_case(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be a complete denial package"):
            SourceCapabilities(
                "cms",
                SourceClass.REGULATOR_SUMMARY,
                frozenset({EvaluationTask.APPEAL_TYPE}),
                complete_denial_package=True,
            )

    def test_clinical_ground_truth_requires_complete_package(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires a complete denial package"):
            SourceCapabilities(
                "partial",
                SourceClass.RECONSTRUCTED_PUBLIC_CASE,
                frozenset({EvaluationTask.POLICY_CRITERIA}),
                clinical_ground_truth=True,
            )

    def test_case_rejects_task_outside_source_capabilities(self) -> None:
        case = cms_case("case-1", "exception", "upheld")
        expanded = AppealCasePackage(
            **{
                **case.__dict__,
                "allowed_tasks": case.allowed_tasks | {EvaluationTask.EVIDENCE_SELECTION},
            }
        )
        with self.assertRaisesRegex(ValueError, "unsupported tasks: evidence_selection"):
            expanded.require_compatible(cms_capabilities())

    def test_prediction_rejects_claim_in_both_support_sets(self) -> None:
        with self.assertRaisesRegex(ValueError, "both supported and unsupported"):
            AppealPrediction(
                "case-1",
                MODEL_HASH,
                POLICY_HASH,
                "revision",
                supported_claim_ids=("claim-1",),
                unsupported_claim_ids=("claim-1",),
            )

    def test_evidence_label_requires_known_disposition(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported evidence disposition"):
            EvidenceLabel("evidence-1", "criterion-1", "maybe")


class EvaluationScoringTests(unittest.TestCase):
    def test_scores_selective_accuracy_sets_and_abstentions(self) -> None:
        cases = (
            cms_case("case-1", "exception", "upheld"),
            cms_case("case-2", "standard", "overturned"),
        )
        second = prediction("case-2", None, "upheld")
        second = AppealPrediction(
            **{
                **second.__dict__,
                "abstained_tasks": frozenset({EvaluationTask.APPEAL_TYPE}),
            }
        )
        report = evaluate_predictions(
            cms_capabilities(),
            cases,
            (prediction("case-1", "exception", "upheld"), second),
        )
        metrics = {(metric.task, metric.metric): metric for metric in report.metrics}

        appeal_type = metrics[(EvaluationTask.APPEAL_TYPE, "selective_accuracy")]
        self.assertEqual(appeal_type.value, 1.0)
        self.assertEqual(appeal_type.denominator, 1)
        self.assertEqual(appeal_type.abstentions, 1)
        outcome = metrics[(EvaluationTask.REGULATOR_OUTCOME, "selective_accuracy")]
        self.assertEqual(outcome.value, 0.5)
        coverage_precision = metrics[(EvaluationTask.COVERAGE_RULES, "micro_precision")]
        coverage_recall = metrics[(EvaluationTask.COVERAGE_RULES, "micro_recall")]
        self.assertEqual(coverage_precision.value, 1.0)
        self.assertEqual(coverage_recall.value, 0.5)

    def test_rejects_incomplete_prediction_coverage(self) -> None:
        cases = (cms_case("case-1", "exception", "upheld"), cms_case("case-2", "standard", "overturned"))
        with self.assertRaisesRegex(ValueError, "prediction coverage mismatch"):
            evaluate_predictions(cms_capabilities(), cases, (prediction("case-1", "exception", "upheld"),))

    def test_wilson_interval_validates_inputs(self) -> None:
        low, high = wilson_interval(5, 10)
        self.assertLess(low, 0.5)
        self.assertGreater(high, 0.5)
        with self.assertRaisesRegex(ValueError, "total must be positive"):
            wilson_interval(0, 0)


if __name__ == "__main__":
    unittest.main()
