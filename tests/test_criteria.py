from __future__ import annotations

import unittest

from appeal_core import (
    CriterionLogic,
    CriterionStatus,
    DraftClaim,
    EvidenceDisposition,
    EvidenceFloorViolation,
    EvidenceObservation,
    EvidenceRef,
    PolicyCriterion,
    SourceSpan,
    evaluate_criterion,
    validate_claims,
)


HASH = "c" * 64


def leaf(criterion_id: str, text: str) -> PolicyCriterion:
    return PolicyCriterion(
        policy_id="policy-real-001",
        payer="Published Payer",
        section_ref="medical-necessity.1",
        cpt_codes=("00000",),
        effective_date="2026-01-01",
        criterion_id=criterion_id,
        text=text,
        logic=CriterionLogic.LEAF,
        children=(),
        satisfied_by=("Condition",),
        source_hash=HASH,
        source_span=SourceSpan(HASH, 10, 10 + len(text), text),
    )


def tree() -> PolicyCriterion:
    imaging = leaf("criterion.imaging", "documented imaging")
    duration = leaf("criterion.duration", "documented symptom duration")
    conservative = leaf("criterion.conservative", "failed conservative therapy")
    alternative = PolicyCriterion(
        policy_id=imaging.policy_id,
        payer=imaging.payer,
        section_ref=imaging.section_ref,
        cpt_codes=imaging.cpt_codes,
        effective_date=imaging.effective_date,
        criterion_id="criterion.alternative",
        text="documented imaging OR documented symptom duration",
        logic=CriterionLogic.OR,
        children=(imaging, duration),
        satisfied_by=(),
        source_hash=HASH,
        source_span=SourceSpan(HASH, 10, 70, "documented imaging OR documented symptom duration"),
    )
    return PolicyCriterion(
        policy_id=imaging.policy_id,
        payer=imaging.payer,
        section_ref=imaging.section_ref,
        cpt_codes=imaging.cpt_codes,
        effective_date=imaging.effective_date,
        criterion_id="criterion.root",
        text="failed conservative therapy AND (imaging OR symptom duration)",
        logic=CriterionLogic.AND,
        children=(conservative, alternative),
        satisfied_by=(),
        source_hash=HASH,
        source_span=SourceSpan(HASH, 0, 80, "failed conservative therapy AND (imaging OR symptom duration)"),
    )


def observation(observation_id: str, leaf_id: str, disposition: EvidenceDisposition) -> EvidenceObservation:
    refs = () if disposition is EvidenceDisposition.ABSENT else (EvidenceRef("FHIR.Condition", f"fhir://synthetic/{leaf_id}", "d" * 64),)
    return EvidenceObservation(observation_id, leaf_id, disposition, "Condition", refs)


class CriteriaTests(unittest.TestCase):
    def test_nested_boolean_tree_does_not_flatten(self) -> None:
        observations = (
            observation("obs.conservative", "criterion.conservative", EvidenceDisposition.SATISFIED),
            observation("obs.duration", "criterion.duration", EvidenceDisposition.SATISFIED),
        )
        result = evaluate_criterion(tree(), observations)
        self.assertEqual(result.status, CriterionStatus.SATISFIED)

        absent_imaging = (
            observation("obs.conservative", "criterion.conservative", EvidenceDisposition.SATISFIED),
            observation("obs.imaging", "criterion.imaging", EvidenceDisposition.ABSENT),
            observation("obs.duration", "criterion.duration", EvidenceDisposition.ABSENT),
        )
        self.assertEqual(evaluate_criterion(tree(), absent_imaging).status, CriterionStatus.ABSENT)

        contradicted_alternatives = (
            observation("obs.conservative", "criterion.conservative", EvidenceDisposition.SATISFIED),
            observation("obs.imaging", "criterion.imaging", EvidenceDisposition.CONTRADICTED),
            observation("obs.duration", "criterion.duration", EvidenceDisposition.CONTRADICTED),
        )
        self.assertEqual(evaluate_criterion(tree(), contradicted_alternatives).status, CriterionStatus.CONTRADICTED)

    def test_absent_is_first_class_and_cannot_support_a_claim(self) -> None:
        observations = (
            observation("obs.conservative", "criterion.conservative", EvidenceDisposition.ABSENT),
            observation("obs.imaging", "criterion.imaging", EvidenceDisposition.ABSENT),
            observation("obs.duration", "criterion.duration", EvidenceDisposition.ABSENT),
        )
        result = evaluate_criterion(tree(), observations)
        claim = DraftClaim("claim-fabricated", "criterion.root", "The patient tried therapy.", "supported", ("obs.conservative",))
        with self.assertRaises(EvidenceFloorViolation):
            validate_claims(tree(), result, observations, (claim,))

    def test_supported_claim_requires_surfaced_fhir_reference(self) -> None:
        observations = (
            observation("obs.conservative", "criterion.conservative", EvidenceDisposition.SATISFIED),
            observation("obs.duration", "criterion.duration", EvidenceDisposition.SATISFIED),
        )
        result = evaluate_criterion(tree(), observations)
        valid = DraftClaim("claim-supported", "criterion.root", "The surfaced record supports the criterion.", "supported", ("obs.conservative", "obs.duration"))
        self.assertEqual(validate_claims(tree(), result, observations, (valid,)), (valid,))

    def test_absence_claim_can_be_valid_without_inventing_record(self) -> None:
        observations = (
            observation("obs.conservative", "criterion.conservative", EvidenceDisposition.ABSENT),
            observation("obs.imaging", "criterion.imaging", EvidenceDisposition.ABSENT),
            observation("obs.duration", "criterion.duration", EvidenceDisposition.ABSENT),
        )
        result = evaluate_criterion(tree(), observations)
        valid = DraftClaim("claim-absence", "criterion.root", "The chart contains no surfaced support for the criterion.", "absence", ("obs.conservative", "obs.imaging", "obs.duration"))
        self.assertEqual(validate_claims(tree(), result, observations, (valid,)), (valid,))

    def test_criterion_fingerprint_is_stable(self) -> None:
        self.assertEqual(tree().fingerprint(), tree().fingerprint())


if __name__ == "__main__":
    unittest.main()
