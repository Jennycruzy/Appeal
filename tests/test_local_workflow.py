from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from appeal_agents.demo import demo_input
from appeal_agents.workflow import AppealWorkflow
from appeal_core import CaseState, CaseStateMachine, DeadlineCatalog, ReceiptLedger


ROOT = Path(__file__).resolve().parents[1]


def workflow(ledger_path: Path | None = None) -> AppealWorkflow:
    ledger = ReceiptLedger(ledger_path) if ledger_path is not None else None
    return AppealWorkflow(
        CaseStateMachine(DeadlineCatalog.from_path(ROOT / "config" / "deadlines.yaml")),
        ledger=ledger,
    )


class LocalWorkflowTests(unittest.TestCase):
    def test_clean_case_stops_at_the_clinician_veto(self) -> None:
        result = workflow().run(demo_input())
        self.assertEqual(result.outcome.value, "awaiting_clinician")
        self.assertEqual(result.case_state, CaseState.AWAITING_CLINICIAN)
        self.assertIsNotNone(result.draft)
        self.assertIsNotNone(result.combinator)
        assert result.combinator is not None
        self.assertEqual(result.combinator.status.value, "needs_human")
        self.assertEqual({verdict.holder for verdict in result.combinator.verdicts}, {
            "criterion_tree",
            "evidence_floor",
            "model_armor_plus_gemma_tripwire",
            "clinician",
        })
        self.assertEqual({event.agent for event in result.events}, {
            "deadline_sentinel",
            "intake",
            "denial_parser",
            "policy_analyst",
            "evidence_miner",
            "argument_builder",
            "veto_combinator",
            "escalation_strategist",
        })

    def test_approved_case_uses_one_submission_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "receipts.jsonl"
            result = workflow(ledger_path).run(demo_input(), clinician_decision=True)
            self.assertEqual(result.outcome.value, "submitted")
            self.assertEqual(result.case_state, CaseState.AWAITING_DETERMINATION)
            self.assertEqual(result.mutation_count, 1)
            verified = ReceiptLedger(ledger_path).verify()
            self.assertGreaterEqual(verified.entry_count, 1)
            self.assertEqual(
                sum(event.status == "mutated_once" for event in result.events),
                1,
            )
            raw_receipts = ledger_path.read_text(encoding="utf-8")
            self.assertEqual(raw_receipts.count('"action":"submission_mutation"'), 1)

    def test_injection_is_quarantined_before_denial_parsing(self) -> None:
        result = workflow().run(demo_input(injection=True))
        self.assertEqual(result.outcome.value, "quarantined")
        self.assertEqual(result.case_state, CaseState.QUARANTINED)
        self.assertEqual(result.mutation_count, 0)
        self.assertIsNone(result.draft)
        self.assertFalse(any(event.agent == "denial_parser" for event in result.events))

    def test_missing_evidence_abstains_without_a_fabricated_draft(self) -> None:
        result = workflow().run(demo_input(missing_evidence=True))
        self.assertEqual(result.outcome.value, "abstained")
        self.assertEqual(result.case_state, CaseState.EVIDENCE_INSUFFICIENT)
        self.assertIsNone(result.draft)
        self.assertEqual(result.mutation_count, 0)

    def test_public_result_omits_draft_prose(self) -> None:
        result = workflow().run(demo_input())
        public = result.to_public_json()
        self.assertIsNone(public["draft"].get("text") if isinstance(public["draft"], dict) else None)
        self.assertNotIn("advanced imaging", str(public))
        self.assertNotIn("chronic knee pain", str(public))

    def test_public_result_exposes_a_source_bound_clinician_record(self) -> None:
        public = workflow().run(demo_input()).to_public_json()
        review = public["review"]
        assert isinstance(review, dict)
        denial = review["denial"]
        policy = review["policy"]
        self.assertIsInstance(denial, dict)
        self.assertIsInstance(policy, dict)
        assert isinstance(denial, dict)
        assert isinstance(policy, dict)
        self.assertEqual(set(denial), {"reason_code", "policy_reference", "source_spans"})
        self.assertNotIn("quote", str(policy))
        self.assertGreater(len(review["observations"]), 0)
        self.assertGreater(len(review["claims"]), 0)

    def test_graph_exposes_the_seven_roles_and_control_edges(self) -> None:
        instance = workflow()
        self.assertEqual(
            set(instance.graph.nodes),
            {
                "intake",
                "denial_parser",
                "policy_analyst",
                "evidence_miner",
                "argument_builder",
                "deadline_sentinel",
                "escalation_strategist",
                "veto_combinator",
                "submission_gate",
            },
        )
        self.assertIn(("veto_combinator", "submission_gate"), instance.graph.edges)

    def test_unfavorable_determination_rederives_the_level_two_argument(self) -> None:
        instance = workflow()
        submitted = instance.run(demo_input(), clinician_decision=True)
        self.assertEqual(submitted.case_state, CaseState.AWAITING_DETERMINATION)
        assert submitted.draft is not None
        first_text = submitted.draft.text
        escalated = instance.process_determination(
            submitted,
            favorable=False,
            at=demo_input().received_at,
        )
        self.assertEqual(escalated.outcome.value, "escalation_ready")
        self.assertEqual(escalated.case_state, CaseState.ESCALATION_ELIGIBLE)
        assert escalated.draft is not None
        self.assertNotEqual(escalated.draft.text, first_text)
        self.assertIn("Level-two", escalated.draft.text)
        self.assertTrue(any(event.status == "rederived" for event in escalated.events))

    def test_expired_clock_abandons_before_a_late_determination(self) -> None:
        instance = workflow()
        submitted = instance.run(demo_input(), clinician_decision=True)
        late = instance.process_determination(
            submitted,
            favorable=True,
            at=demo_input().received_at.replace(month=9, day=6),
        )
        self.assertEqual(late.outcome.value, "deadline_abandoned")
        self.assertEqual(late.case_state, CaseState.CLOSED_ABANDONED_DEADLINE)


if __name__ == "__main__":
    unittest.main()
