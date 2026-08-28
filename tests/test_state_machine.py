from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from pathlib import Path

from appeal_core import (
    Actor,
    ActorKind,
    CaseState,
    CaseStateMachine,
    DecisionSource,
    DeadlineCatalog,
    EvidenceRef,
    HumanReleaseRequired,
    IdempotencyConflict,
    InvalidTransition,
    SignatureRequired,
    UnverifiedDeadline,
)


ROOT = Path(__file__).resolve().parents[1]
DEADLINES = DeadlineCatalog.from_path(ROOT / "config" / "deadlines.yaml")
MACHINE = CaseStateMachine(DEADLINES)
TIME = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
AGENT = Actor("denial-parser-identity", ActorKind.AGENT)
DETERMINISTIC = DecisionSource("deterministic", "case-state-machine", "0.1")
HUMAN = Actor("clinician-demo", ActorKind.HUMAN)
SIGNATURE = EvidenceRef("ClinicianSignature", "signature://case-001/1", "a" * 64)


def move(case, state, *, at=TIME, actor=AGENT, source=DETERMINISTIC, reason="test transition", refs=(), key="unique"):
    return MACHINE.transition(case, state, at, actor, source, reason, refs, key, SIGNATURE if state is CaseState.SUBMITTED_LEVEL_1 else None)


class StateMachineTests(unittest.TestCase):
    def test_valid_path_is_explicit_and_serializable(self) -> None:
        case = MACHINE.create("case-001", "tenant-a", TIME, AGENT, DETERMINISTIC)
        case = move(case, CaseState.DENIAL_PARSED, key="case-001:parse")
        case = move(case, CaseState.POLICY_LOCATED, key="case-001:policy")
        case = move(case, CaseState.CRITERION_IDENTIFIED, key="case-001:criterion")
        case = move(case, CaseState.EVIDENCE_ASSEMBLED, key="case-001:evidence")
        case = move(case, CaseState.DRAFT_READY, key="case-001:draft")
        case = move(case, CaseState.AWAITING_CLINICIAN, key="case-001:review")
        case = move(case, CaseState.SUBMITTED_LEVEL_1, actor=HUMAN, source=DecisionSource("human", "clinician-signature", "1"), key="case-001:submit")
        self.assertEqual(case.state, CaseState.SUBMITTED_LEVEL_1)
        document = case.to_json()
        self.assertEqual(document["case_id"], "case-001")
        self.assertEqual(len(case.transitions), 8)
        self.assertEqual(len(case.fingerprint()), 64)

    def test_invalid_transition_fails_loudly(self) -> None:
        case = MACHINE.create("case-002", "tenant-a", TIME, AGENT, DETERMINISTIC)
        with self.assertRaises(InvalidTransition):
            move(case, CaseState.SUBMITTED_LEVEL_1, key="case-002:bad")

    def test_submission_requires_signature(self) -> None:
        case = MACHINE.create("case-003", "tenant-a", TIME, AGENT, DETERMINISTIC)
        for state, key in [
            (CaseState.DENIAL_PARSED, "parse"),
            (CaseState.POLICY_LOCATED, "policy"),
            (CaseState.CRITERION_IDENTIFIED, "criterion"),
            (CaseState.EVIDENCE_ASSEMBLED, "evidence"),
            (CaseState.DRAFT_READY, "draft"),
            (CaseState.AWAITING_CLINICIAN, "review"),
        ]:
            case = move(case, state, key=f"case-003:{key}")
        with self.assertRaises(SignatureRequired):
            MACHINE.transition(case, CaseState.SUBMITTED_LEVEL_1, TIME, HUMAN, DecisionSource("human", "clinician", "1"), "unsigned", (), "case-003:submit")

    def test_abstention_and_missed_deadline_are_reachable(self) -> None:
        case = MACHINE.create("case-004", "tenant-a", TIME, AGENT, DETERMINISTIC)
        case = move(case, CaseState.DENIAL_PARSED, key="case-004:parse")
        case = move(case, CaseState.POLICY_NOT_FOUND_HUMAN_REVIEW, key="case-004:abstain")
        self.assertEqual(case.state, CaseState.POLICY_NOT_FOUND_HUMAN_REVIEW)

        missed = MACHINE.create("case-005", "tenant-a", TIME, AGENT, DETERMINISTIC)
        missed = move(missed, CaseState.DENIAL_PARSED, key="case-005:parse")
        missed = move(missed, CaseState.POLICY_LOCATED, key="case-005:policy")
        missed = move(missed, CaseState.CRITERION_IDENTIFIED, key="case-005:criterion")
        missed = move(missed, CaseState.EVIDENCE_INSUFFICIENT, key="case-005:insufficient")
        missed = move(missed, CaseState.CLOSED_ABANDONED_DEADLINE, key="case-005:abandoned")
        self.assertEqual(missed.state, CaseState.CLOSED_ABANDONED_DEADLINE)

    def test_duplicate_delivery_is_idempotent_and_conflict_is_rejected(self) -> None:
        case = MACHINE.create("case-006", "tenant-a", TIME, AGENT, DETERMINISTIC)
        first = move(case, CaseState.DENIAL_PARSED, key="case-006:parse")
        replay = move(first, CaseState.DENIAL_PARSED, key="case-006:parse")
        self.assertEqual(first.fingerprint(), replay.fingerprint())
        with self.assertRaises(IdempotencyConflict):
            move(first, CaseState.PARSE_FAILED_HUMAN_REVIEW, reason="different", key="case-006:parse")

    def test_verified_and_unverified_deadlines_are_distinct(self) -> None:
        case = MACHINE.create("case-007", "tenant-a", TIME, AGENT, DETERMINISTIC)
        case = move(case, CaseState.DENIAL_PARSED, key="case-007:parse")
        self.assertEqual(MACHINE.deadline_at(case), datetime(2026, 9, 1, 12, 0, tzinfo=UTC))
        case = move(case, CaseState.POLICY_LOCATED, key="case-007:policy")
        case = move(case, CaseState.CRITERION_IDENTIFIED, key="case-007:criterion")
        case = move(case, CaseState.EVIDENCE_ASSEMBLED, key="case-007:evidence")
        case = move(case, CaseState.DRAFT_READY, key="case-007:draft")
        case = move(case, CaseState.AWAITING_CLINICIAN, key="case-007:review")
        case = move(case, CaseState.SUBMITTED_LEVEL_1, actor=HUMAN, source=DecisionSource("human", "clinician-signature", "1"), key="case-007:submit")
        case = move(case, CaseState.AWAITING_DETERMINATION, key="case-007:await")
        self.assertEqual(MACHINE.deadline_at(case), datetime(2026, 9, 1, 12, 0, tzinfo=UTC))
        case = move(case, CaseState.DETERMINATION_RECEIVED, key="case-007:determination")
        case = move(case, CaseState.ESCALATION_ELIGIBLE, key="case-007:eligible")
        with self.assertRaises(UnverifiedDeadline):
            MACHINE.deadline_at(case)

    def test_case_clock_is_first_class_and_quarantine_release_is_human_only(self) -> None:
        case = MACHINE.create("case-009", "tenant-a", TIME, AGENT, DETERMINISTIC)
        clock = MACHINE.statutory_clock(case)
        self.assertEqual(clock.deadline_key, "intake_unverified")
        self.assertIsNone(clock.to_json()["expires_at"])
        with self.assertRaises(UnverifiedDeadline):
            clock.remaining_seconds(TIME)
        with self.assertRaises(HumanReleaseRequired):
            MACHINE.transition(
                MACHINE.transition(case, CaseState.QUARANTINED, TIME, AGENT, DETERMINISTIC, "blocked", (), "case-009:quarantine"),
                CaseState.INTAKE_RECEIVED,
                TIME,
                AGENT,
                DETERMINISTIC,
                "release",
                (),
                "case-009:release",
            )

    def test_fingerprint_is_byte_stable_for_same_state(self) -> None:
        left = MACHINE.create("case-008", "tenant-a", TIME, AGENT, DETERMINISTIC)
        right = MACHINE.create("case-008", "tenant-a", TIME, AGENT, DETERMINISTIC)
        self.assertEqual(json.dumps(left.to_json(), sort_keys=True, separators=(",", ":")), json.dumps(right.to_json(), sort_keys=True, separators=(",", ":")))
        self.assertEqual(left.fingerprint(), right.fingerprint())


if __name__ == "__main__":
    unittest.main()
