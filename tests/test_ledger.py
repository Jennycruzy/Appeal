from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from appeal_core import (
    Actor,
    ActorKind,
    DecisionSource,
    EvidenceRef,
    LedgerIntegrityError,
    ReceiptDraft,
    ReceiptIdempotencyConflict,
    ReceiptLedger,
)


TIME = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
ACTOR = Actor("deadline-sentinel-identity", ActorKind.SCHEDULER)
SOURCE = DecisionSource("deterministic", "deadline-sentinel", "0.1")
EVIDENCE = (EvidenceRef("CaseState", "case://case-001/state", "b" * 64),)


def draft(receipt_id: str, key: str, *, outcome="allowed", refusal_reason=None) -> ReceiptDraft:
    return ReceiptDraft(
        receipt_id=receipt_id,
        recorded_at=TIME,
        tenant_id="tenant-a",
        case_id="case-001",
        actor=ACTOR,
        action="deadline_check",
        decision_source=SOURCE,
        evidence_refs=EVIDENCE,
        outcome=outcome,
        reason="case remains within the configured clock",
        idempotency_key=key,
        refusal_reason=refusal_reason,
    )


class LedgerTests(unittest.TestCase):
    def test_append_verify_and_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = ReceiptLedger(Path(directory) / "receipts.jsonl")
            first = ledger.append(draft("receipt-001", "effect-001"))
            second = ledger.append(draft("receipt-002", "effect-002"))
            result = ledger.verify()
            self.assertEqual(result.entry_count, 2)
            self.assertEqual(first.body["previous_hash"], "0" * 64)
            self.assertEqual(second.body["previous_hash"], first.entry_hash)
            self.assertEqual(result.tip_hash, second.entry_hash)

    def test_duplicate_delivery_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = ReceiptLedger(Path(directory) / "receipts.jsonl")
            first = ledger.append(draft("receipt-003", "effect-003"))
            replay = ledger.append(draft("receipt-003", "effect-003"))
            self.assertEqual(first.serialized(), replay.serialized())
            self.assertEqual(ledger.verify().entry_count, 1)
            with self.assertRaises(ReceiptIdempotencyConflict):
                ledger.append(draft("receipt-004", "effect-003"))

    def test_refusal_requires_reason(self) -> None:
        with self.assertRaises(ValueError):
            draft("receipt-005", "effect-005", outcome="refused")
        valid = draft("receipt-006", "effect-006", outcome="refused", refusal_reason="PHI egress blocked")
        self.assertEqual(valid.refusal_reason, "PHI egress blocked")

    def test_tampering_fails_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipts.jsonl"
            ledger = ReceiptLedger(path)
            ledger.append(draft("receipt-007", "effect-007"))
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["reason"] = "altered after append"
            path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            with self.assertRaises(LedgerIntegrityError):
                ledger.verify()


if __name__ == "__main__":
    unittest.main()
