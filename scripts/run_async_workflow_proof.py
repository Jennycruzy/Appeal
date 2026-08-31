"""Exercise restart-safe payer/evidence wakes and deadline handling locally.

The report contains only case states, event identifiers, counts, hashes, and
control outcomes. Synthetic denial/chart bodies stay in transient memory and
the receipt ledger is written outside the repository by default.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from appeal_agents.demo import demo_input
from appeal_agents.workflow import AppealWorkflow
from appeal_core import CaseState, CaseStateMachine, DeadlineCatalog, ReceiptLedger
from appeal_platform import (
    EVIDENCE_ARRIVAL_TOPIC,
    PAYER_DETERMINATION_TOPIC,
    DomainEvent,
    LocalCaseRuntime,
)
from appeal_service import LocalAppealService


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
DEFAULT_OUTPUT = ROOT / "evidence" / "async-workflow-proof.json"
DEFAULT_LEDGER = ROOT.parent / "Downloads" / "appeal-async-workflow-proof-receipts.jsonl"


def _workflow(ledger: ReceiptLedger) -> AppealWorkflow:
    deadlines = DeadlineCatalog.from_path(ROOT / "config" / "deadlines.yaml")
    return AppealWorkflow(CaseStateMachine(deadlines), ledger=ledger)


def _outside_repository(path: Path) -> None:
    resolved = path.expanduser().resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise ValueError("receipt ledger must remain outside the repository")


def _case_snapshot(runtime: LocalCaseRuntime, tenant_id: str, case_id: str) -> dict[str, object]:
    case = runtime.store.require(tenant_id, case_id)
    return {
        "case_state": case.state.value,
        "case_fingerprint": case.fingerprint(),
        "transition_count": len(case.transitions),
        "external_mutation_count": sum(
            transition.to_state is CaseState.SUBMITTED_LEVEL_1 for transition in case.transitions
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    args = parser.parse_args()
    _outside_repository(args.ledger)
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    ledger = ReceiptLedger(args.ledger)

    evidence_input = demo_input(
        missing_evidence=True,
        case_id="case-demo-async-evidence",
        tenant_id="tenant-demo-async",
    )
    evidence_runtime = LocalCaseRuntime(_workflow(ledger))
    waiting = evidence_runtime.start(evidence_input, at=NOW)
    assert waiting.workflow.case_state is CaseState.EVIDENCE_INSUFFICIENT
    waiting_session = evidence_runtime.session_store.get(
        evidence_input.tenant_id,
        evidence_input.case_id,
    )
    assert waiting_session is not None
    waiting_session_json = waiting_session.to_json()
    assert evidence_input.patient_id not in str(waiting_session_json)
    evidence_initial = _case_snapshot(evidence_runtime, evidence_input.tenant_id, evidence_input.case_id)

    def resolve_evidence(tenant_id: str, case_id: str):
        if (tenant_id, case_id) != (evidence_input.tenant_id, evidence_input.case_id):
            return None
        return demo_input(case_id=case_id, tenant_id=tenant_id)

    evidence_restart = LocalCaseRuntime(
        _workflow(ledger),
        store=evidence_runtime.store,
        spine=evidence_runtime.spine,
        session_store=evidence_runtime.session_store,
        reversibility=evidence_runtime.reversibility,
        input_resolver=resolve_evidence,
    )
    evidence_service = LocalAppealService(evidence_restart)
    evidence_event = DomainEvent.create(
        evidence_input.tenant_id,
        evidence_input.case_id,
        EVIDENCE_ARRIVAL_TOPIC,
        f"{evidence_input.case_id}:evidence:revision-2",
        NOW + timedelta(minutes=5),
        {"evidence_revision": "revision-2", "evidence_ref_count": 2},
    )
    evidence_resume = evidence_service.accept_event(evidence_event)
    evidence_duplicate = evidence_service.accept_event(evidence_event)
    assert evidence_resume["workflow"]["status"] == "resumed"  # type: ignore[index]
    assert evidence_duplicate["workflow"]["status"] == "duplicate"  # type: ignore[index]
    assert evidence_restart.store.require(evidence_input.tenant_id, evidence_input.case_id).state is CaseState.AWAITING_CLINICIAN

    no_progress_input = demo_input(
        missing_evidence=True,
        case_id="case-demo-async-no-progress",
        tenant_id="tenant-demo-async",
    )
    no_progress_runtime = LocalCaseRuntime(_workflow(ledger))
    no_progress_runtime.start(no_progress_input, at=NOW)

    def resolve_no_progress(tenant_id: str, case_id: str):
        if (tenant_id, case_id) != (no_progress_input.tenant_id, no_progress_input.case_id):
            return None
        return demo_input(missing_evidence=True, case_id=case_id, tenant_id=tenant_id)

    no_progress_restart = LocalCaseRuntime(
        _workflow(ledger),
        store=no_progress_runtime.store,
        spine=no_progress_runtime.spine,
        session_store=no_progress_runtime.session_store,
        input_resolver=resolve_no_progress,
    )
    no_progress_event = DomainEvent.create(
        no_progress_input.tenant_id,
        no_progress_input.case_id,
        EVIDENCE_ARRIVAL_TOPIC,
        f"{no_progress_input.case_id}:evidence:still-missing",
        NOW + timedelta(minutes=5),
        {"evidence_revision": "revision-still-missing", "evidence_ref_count": 1},
    )
    no_progress_first = no_progress_restart.handle_event(no_progress_event)
    no_progress_duplicate = no_progress_restart.handle_event(no_progress_event)
    assert no_progress_first["status"] == "resumed"
    assert no_progress_first["case_state"] == CaseState.EVIDENCE_INSUFFICIENT.value
    assert no_progress_duplicate["status"] == "duplicate"

    payer_input = demo_input(
        case_id="case-demo-async-payer",
        tenant_id="tenant-demo-async",
    )
    payer_runtime = LocalCaseRuntime(_workflow(ledger))
    payer_waiting = payer_runtime.start(payer_input, at=NOW)
    payer_submitted = payer_runtime.approve(payer_waiting, at=NOW + timedelta(minutes=5))
    assert payer_submitted.workflow.case_state is CaseState.AWAITING_DETERMINATION
    payer_initial = _case_snapshot(payer_runtime, payer_input.tenant_id, payer_input.case_id)
    payer_restart = LocalCaseRuntime(
        _workflow(ledger),
        store=payer_runtime.store,
        spine=payer_runtime.spine,
        session_store=payer_runtime.session_store,
        reversibility=payer_runtime.reversibility,
    )
    payer_service = LocalAppealService(payer_restart)
    payer_event = DomainEvent.create(
        payer_input.tenant_id,
        payer_input.case_id,
        PAYER_DETERMINATION_TOPIC,
        f"{payer_input.case_id}:payer:decision-1",
        NOW + timedelta(hours=6),
        {
            "decision": "favorable",
            "criterion_status": "satisfied",
            "evidence_ref_count": 2,
        },
    )
    payer_resume = payer_service.accept_event(payer_event)
    payer_duplicate = payer_service.accept_event(payer_event)
    assert payer_resume["workflow"]["status"] == "resumed"  # type: ignore[index]
    assert payer_duplicate["workflow"]["status"] == "duplicate"  # type: ignore[index]
    assert payer_restart.store.require(payer_input.tenant_id, payer_input.case_id).state is CaseState.CLOSED_WON
    assert payer_restart.reversibility.verify().entry_count == 1

    deadline_input = demo_input(
        case_id="case-demo-async-deadline",
        tenant_id="tenant-demo-async",
    )
    deadline_runtime = LocalCaseRuntime(_workflow(ledger))
    deadline_waiting = deadline_runtime.start(deadline_input, at=NOW)
    deadline_runtime.approve(deadline_waiting, at=NOW + timedelta(minutes=5))
    deadline_tick = deadline_runtime.sentinel_tick(at=NOW + timedelta(days=8))
    assert deadline_tick.abandoned_count == 1
    assert deadline_runtime.store.require(deadline_input.tenant_id, deadline_input.case_id).state is CaseState.CLOSED_ABANDONED_DEADLINE

    verification = ledger.verify()
    report: dict[str, object] = {
        "schema_version": "0.1",
        "kind": "durable_async_workflow_proof",
        "recorded_at": NOW.isoformat().replace("+00:00", "Z"),
        "execution_scope": "local_deterministic_restart_harness",
        "synthetic_only": True,
        "raw_content_persisted": False,
        "hosted_follow_up_required": True,
        "evidence_resume": {
            "initial": evidence_initial,
            "restart_rehydrated": evidence_restart.resume(evidence_input.tenant_id, evidence_input.case_id) is not None,
            "event_id": evidence_event.event_id,
            "event_payload_fields": ["evidence_ref_count", "evidence_revision"],
            "resume_status": evidence_resume["workflow"]["status"],  # type: ignore[index]
            "resume_case_state": evidence_resume["workflow"]["case_state"],  # type: ignore[index]
            "duplicate_status": evidence_duplicate["workflow"]["status"],  # type: ignore[index]
            "final": _case_snapshot(evidence_restart, evidence_input.tenant_id, evidence_input.case_id),
            "reference_only_session": waiting_session_json["persistence_policy"],
            "patient_scope_hash_persisted": waiting_session_json.get("patient_scope_hash") is not None,
        },
        "no_progress_retry": {
            "event_id": no_progress_event.event_id,
            "resume_status": no_progress_first["status"],
            "case_state": no_progress_first["case_state"],
            "duplicate_status": no_progress_duplicate["status"],
            "processed_event_count": len(
                no_progress_restart.session_store.get(
                    no_progress_input.tenant_id,
                    no_progress_input.case_id,
                ).processed_event_ids  # type: ignore[union-attr]
            ),
        },
        "payer_resume": {
            "initial": payer_initial,
            "approved_before_restart": payer_submitted.workflow.case_state.value,
            "restart_rehydrated": payer_restart.resume(payer_input.tenant_id, payer_input.case_id) is not None,
            "event_id": payer_event.event_id,
            "event_payload_fields": ["criterion_status", "decision", "evidence_ref_count"],
            "resume_status": payer_resume["workflow"]["status"],  # type: ignore[index]
            "resume_case_state": payer_resume["workflow"]["case_state"],  # type: ignore[index]
            "resume_mutation_count": payer_resume["workflow"]["mutation_count"],  # type: ignore[index]
            "duplicate_status": payer_duplicate["workflow"]["status"],  # type: ignore[index]
            "final": _case_snapshot(payer_restart, payer_input.tenant_id, payer_input.case_id),
            "reversibility_entry_count": payer_restart.reversibility.verify().entry_count,
        },
        "deadline_scheduler": {
            "case_id": deadline_input.case_id,
            "tick_at": (NOW + timedelta(days=8)).isoformat().replace("+00:00", "Z"),
            "inspected_count": deadline_tick.inspected_count,
            "abandoned_count": deadline_tick.abandoned_count,
            "final": _case_snapshot(deadline_runtime, deadline_input.tenant_id, deadline_input.case_id),
        },
        "receipt_chain": {
            "verification": "passed",
            "entry_count": verification.entry_count,
            "tip_hash": verification.tip_hash,
            "ledger_path_outside_repository": True,
        },
        "event_transport": {
            "topics": [EVIDENCE_ARRIVAL_TOPIC, PAYER_DETERMINATION_TOPIC],
            "payload_policy": "reference_only_scalar_metadata",
            "duplicate_delivery_policy": "case_state_and_idempotency_fingerprint",
        },
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"\nMetadata report: {args.output}")
    print(f"Receipt ledger: {args.ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
