from __future__ import annotations

import unittest

from appeal_evaluation import (
    AnnotationDisposition,
    CaseAnnotation,
    OperationalRoute,
    RationaleCategory,
    SourceSpanLabel,
    requires_adjudication,
    route_for,
)


CASE = "a" * 64
SOURCE = "b" * 64


def annotation(
    annotator: str,
    category: RationaleCategory = RationaleCategory.PRIOR_AUTHORIZATION,
) -> CaseAnnotation:
    return CaseAnnotation(
        case_ref=CASE,
        taxonomy_version="cms_part_d_rationale_v1",
        annotator_id=annotator,
        annotator_role="researcher",
        blinded_to_outcome=True,
        disposition=AnnotationDisposition.ANNOTATED,
        primary_category=category,
        secondary_categories=(),
        route=route_for(category),
        rationale_spans=(SourceSpanLabel("decision_rationale", 0, 12, SOURCE),),
        policy_spans=(),
        confidence=4,
    )


class EvaluationAnnotationTests(unittest.TestCase):
    def test_official_category_has_frozen_route(self) -> None:
        self.assertIs(
            route_for(RationaleCategory.QUANTITY_LIMIT),
            OperationalRoute.UTILIZATION_MANAGEMENT_EXCEPTION,
        )

    def test_annotation_requires_outcome_blinding_and_source_span(self) -> None:
        with self.assertRaisesRegex(ValueError, "blinded"):
            CaseAnnotation(
                case_ref=CASE,
                taxonomy_version="cms_part_d_rationale_v1",
                annotator_id="reviewer-a",
                annotator_role="researcher",
                blinded_to_outcome=False,
                disposition=AnnotationDisposition.ANNOTATED,
                primary_category=RationaleCategory.PRIOR_AUTHORIZATION,
                secondary_categories=(),
                route=OperationalRoute.UTILIZATION_MANAGEMENT_EXCEPTION,
                rationale_spans=(SourceSpanLabel("decision_rationale", 0, 12, SOURCE),),
                policy_spans=(),
                confidence=4,
            )
        with self.assertRaisesRegex(ValueError, "requires at least one source span"):
            CaseAnnotation(
                case_ref=CASE,
                taxonomy_version="cms_part_d_rationale_v1",
                annotator_id="reviewer-a",
                annotator_role="researcher",
                blinded_to_outcome=True,
                disposition=AnnotationDisposition.ANNOTATED,
                primary_category=RationaleCategory.PRIOR_AUTHORIZATION,
                secondary_categories=(),
                route=OperationalRoute.UTILIZATION_MANAGEMENT_EXCEPTION,
                rationale_spans=(),
                policy_spans=(),
                confidence=4,
            )

    def test_abstention_has_strict_category_and_route(self) -> None:
        result = CaseAnnotation(
            case_ref=CASE,
            taxonomy_version="cms_part_d_rationale_v1",
            annotator_id="reviewer-a",
            annotator_role="researcher",
            blinded_to_outcome=True,
            disposition=AnnotationDisposition.ABSTAINED,
            primary_category=RationaleCategory.INSUFFICIENT_INFORMATION,
            secondary_categories=(),
            route=OperationalRoute.REQUEST_ADDITIONAL_INFORMATION,
            rationale_spans=(),
            policy_spans=(),
            confidence=3,
        )
        self.assertIs(result.disposition, AnnotationDisposition.ABSTAINED)

    def test_independent_disagreement_requires_adjudication(self) -> None:
        first = annotation("reviewer-a")
        agreeing = annotation("reviewer-b")
        disagreeing = annotation("reviewer-b", RationaleCategory.STEP_THERAPY)
        self.assertFalse(requires_adjudication(first, agreeing))
        self.assertTrue(requires_adjudication(first, disagreeing))


if __name__ == "__main__":
    unittest.main()
