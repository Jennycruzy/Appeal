from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from appeal_evaluation import (
    AnnotationDisposition,
    CaseAnnotation,
    GoldResolution,
    OperationalRoute,
    RationaleCategory,
    SourceSpanLabel,
    annotation_status,
    build_gold_labels,
    inspect_queue,
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


def queue_row(category: RationaleCategory = RationaleCategory.PRIOR_AUTHORIZATION) -> dict[str, object]:
    rationale = "Coverage requires prior authorization before approval."
    policy = "The plan requires prior authorization for this drug."
    return {
        "case_ref": CASE,
        "split": "locked_test",
        "context": {
            "part": "Part D-Drug",
            "appeal_type": "Exception",
            "condition": "Condition",
            "requested_item_or_drug": "Drug",
            "decision_rationale": rationale,
            "policy_context": policy,
        },
        "source_hashes": {
            "decision_rationale": hashlib.sha256(rationale.encode()).hexdigest(),
            "policy_context": hashlib.sha256(policy.encode()).hexdigest(),
        },
        "annotation": {
            "disposition": "annotated",
            "primary_category": category.value,
            "secondary_categories": [],
            "route": route_for(category).value,
            "rationale_spans": [{
                "source_field": "decision_rationale",
                "start": 0,
                "end": len(rationale),
                "source_sha256": hashlib.sha256(rationale.encode()).hexdigest(),
            }],
            "policy_spans": [],
            "confidence": 4,
        },
    }


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

    def test_pending_queues_do_not_claim_gold(self) -> None:
        pending = queue_row()
        pending["annotation"] = {
            "disposition": None,
            "primary_category": None,
            "secondary_categories": [],
            "route": None,
            "rationale_spans": [],
            "policy_spans": [],
            "confidence": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.jsonl"
            path.write_text(json.dumps(pending) + "\n", encoding="utf-8")
            inspection = inspect_queue(
                path,
                taxonomy_version="cms_part_d_rationale_v1",
                annotator_id="reviewer-a",
                annotator_role="researcher",
                require_locked_test=False,
            )
            report = annotation_status(inspection, inspection, taxonomy_version="cms_part_d_rationale_v1", adjudication_path=None)
        self.assertEqual(report["status"], "pending_human_annotation")
        self.assertFalse(report["gold_claim_allowed"])

    def test_agreeing_locked_queues_produce_consensus_gold(self) -> None:
        row = queue_row()
        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "a.jsonl"
            second_path = Path(directory) / "b.jsonl"
            payload = json.dumps(row) + "\n"
            first_path.write_text(payload, encoding="utf-8")
            second_path.write_text(payload, encoding="utf-8")
            first = inspect_queue(first_path, taxonomy_version="cms_part_d_rationale_v1", annotator_id="reviewer-a", annotator_role="researcher", require_locked_test=False)
            second = inspect_queue(second_path, taxonomy_version="cms_part_d_rationale_v1", annotator_id="reviewer-b", annotator_role="researcher", require_locked_test=False)
            labels = build_gold_labels(first, second, adjudication_path=None, taxonomy_version="cms_part_d_rationale_v1")
        self.assertEqual(len(labels), 1)
        self.assertIs(labels[0].resolution, GoldResolution.CONSENSUS)

    def test_disagreement_requires_adjudication_and_adjudicator_is_human(self) -> None:
        first_row = queue_row(RationaleCategory.PRIOR_AUTHORIZATION)
        second_row = queue_row(RationaleCategory.STEP_THERAPY)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_path = root / "a.jsonl"
            second_path = root / "b.jsonl"
            first_path.write_text(json.dumps(first_row) + "\n", encoding="utf-8")
            second_path.write_text(json.dumps(second_row) + "\n", encoding="utf-8")
            first = inspect_queue(first_path, taxonomy_version="cms_part_d_rationale_v1", annotator_id="reviewer-a", annotator_role="researcher", require_locked_test=False)
            second = inspect_queue(second_path, taxonomy_version="cms_part_d_rationale_v1", annotator_id="reviewer-b", annotator_role="researcher", require_locked_test=False)
            with self.assertRaisesRegex(ValueError, "no adjudication"):
                build_gold_labels(first, second, adjudication_path=None, taxonomy_version="cms_part_d_rationale_v1")
            adjudication = root / "adjudication.jsonl"
            adjudication.write_text(json.dumps({
                "case_ref": CASE,
                "resolution": "adjudicated",
                "decision_note": "The rationale names prior authorization as the principal issue.",
                "annotation": first_row["annotation"],
            }) + "\n", encoding="utf-8")
            labels = build_gold_labels(
                first,
                second,
                adjudication_path=adjudication,
                taxonomy_version="cms_part_d_rationale_v1",
                adjudicator_id="utilization-reviewer",
                adjudicator_role="utilization review professional",
            )
        self.assertEqual(labels[0].resolution, GoldResolution.ADJUDICATED)
        self.assertIsNotNone(labels[0].adjudication_note_sha256)

    def test_queue_rejects_outcome_key(self) -> None:
        row = queue_row()
        row["regulator_outcome"] = "favorable"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.jsonl"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outcome labels"):
                inspect_queue(path, taxonomy_version="cms_part_d_rationale_v1", annotator_id="reviewer-a", annotator_role="researcher", require_locked_test=False)

    def test_queue_rejects_span_outside_source_bounds(self) -> None:
        row = queue_row()
        annotation_value = row["annotation"]
        assert isinstance(annotation_value, dict)
        spans = annotation_value["rationale_spans"]
        assert isinstance(spans, list)
        span = spans[0]
        assert isinstance(span, dict)
        span["end"] = 10_000
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.jsonl"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exceeds source bounds"):
                inspect_queue(path, taxonomy_version="cms_part_d_rationale_v1", annotator_id="reviewer-a", annotator_role="researcher", require_locked_test=False)


if __name__ == "__main__":
    unittest.main()
