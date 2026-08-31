"""Seed six safe synthetic cases for a local judge-facing board proof."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from appeal_agents.demo import demo_input
from appeal_agents.models import AppealInput
from appeal_agents.workflow import AppealWorkflow
from appeal_core import CaseState, CaseStateMachine, DeadlineCatalog, ReceiptLedger
from appeal_platform import (
    EVIDENCE_ARRIVAL_TOPIC,
    PAYER_DETERMINATION_TOPIC,
    DomainEvent,
    LocalCaseRuntime,
    PayerDecisionStatus,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "evidence" / "seeded-demo-tenant.json"
DEFAULT_LEDGER = ROOT.parent / "Downloads" / "appeal-seeded-demo-receipts-v2.jsonl"
TENANT_ID = "tenant-demo-seeded"
NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def _workflow(ledger: ReceiptLedger) -> AppealWorkflow:
    deadlines = DeadlineCatalog.from_path(ROOT / "config" / "deadlines.yaml")
    return AppealWorkflow(CaseStateMachine(deadlines), ledger=ledger)


def _snapshot(runtime: LocalCaseRuntime, case_id: str) -> dict[str, object]:
    case = runtime.store.require(TENANT_ID, case_id)
    session = runtime.session_store.get(TENANT_ID, case_id)
    resumed = runtime.resume(TENANT_ID, case_id)
    return {
        "case_id": case_id,
        "case_fingerprint": case.fingerprint(),
        "case_state": case.state.value,
        "outcome": resumed.workflow.outcome.value if resumed is not None else "persisted_metadata",
        "external_mutation_count": sum(
            transition.to_state is CaseState.SUBMITTED_LEVEL_1 for transition in case.transitions
        ),
        "processed_event_count": len(session.processed_event_ids) if session is not None else 0,
        "session_persisted": session is not None,
    }


def _make_input(case_id: str, **flags: bool) -> AppealInput:
    return demo_input(case_id=case_id, tenant_id=TENANT_ID, **flags)


def _start(
    runtime: LocalCaseRuntime,
    inputs: dict[tuple[str, str], AppealInput],
    appeal_input: AppealInput,
    *,
    at: datetime,
):
    inputs[(appeal_input.tenant_id, appeal_input.case_id)] = appeal_input
    return runtime.start(appeal_input, at=at)


def _seed(
    runtime: LocalCaseRuntime,
    inputs: dict[tuple[str, str], AppealInput],
) -> tuple[str, ...]:
    clean = _make_input("case-demo-seeded-clean")
    _start(runtime, inputs, clean, at=NOW)

    injection = _make_input("case-demo-seeded-injection", injection=True)
    _start(runtime, inputs, injection, at=NOW)

    missing = _make_input("case-demo-seeded-missing", missing_evidence=True)
    _start(runtime, inputs, missing, at=NOW)

    evidence = _make_input("case-demo-seeded-evidence", missing_evidence=True)
    _start(runtime, inputs, evidence, at=NOW)
    # The persisted case starts without the chart evidence. The resolver
    # receives the later authorized revision, which contains the two synthetic
    # FHIR references needed to cross the Evidence Floor.
    inputs[(evidence.tenant_id, evidence.case_id)] = _make_input(evidence.case_id)
    evidence_runtime = LocalCaseRuntime(
        runtime.workflow,
        store=runtime.store,
        spine=runtime.spine,
        session_store=runtime.session_store,
        reversibility=runtime.reversibility,
        input_resolver=lambda tenant_id, case_id: inputs.get((tenant_id, case_id)),
    )
    evidence_event = DomainEvent.create(
        TENANT_ID,
        evidence.case_id,
        EVIDENCE_ARRIVAL_TOPIC,
        f"{evidence.case_id}:evidence:seeded-revision",
        NOW + timedelta(hours=2),
        {"evidence_revision": "seeded-revision", "evidence_ref_count": 2},
    )
    evidence_result = evidence_runtime.handle_event(evidence_event, at=NOW + timedelta(hours=2))
    if evidence_result.get("status") != "resumed":
        raise AssertionError(f"evidence seed did not resume: {evidence_result}")

    deadline = _make_input("case-demo-seeded-deadline")
    deadline_waiting = _start(runtime, inputs, deadline, at=NOW)
    runtime.approve(deadline_waiting, at=NOW + timedelta(minutes=5))
    deadline_report = runtime.sentinel_tick(at=NOW + timedelta(days=8))
    if deadline_report.abandoned_count != 1:
        raise AssertionError("deadline seed did not abandon exactly one case")

    escalation = _make_input("case-demo-seeded-escalation")
    escalation_waiting = _start(runtime, inputs, escalation, at=NOW)
    runtime.approve(escalation_waiting, at=NOW + timedelta(minutes=5))
    payer_event = DomainEvent.create(
        TENANT_ID,
        escalation.case_id,
        PAYER_DETERMINATION_TOPIC,
        f"{escalation.case_id}:payer:seeded-unfavorable",
        NOW + timedelta(hours=6),
        {
            "decision": PayerDecisionStatus.UNFAVORABLE.value,
            "criterion_status": "contradicted",
            "evidence_ref_count": 2,
        },
    )
    escalation_result = runtime.handle_event(payer_event, at=NOW + timedelta(hours=6))
    if escalation_result.get("status") != "resumed":
        raise AssertionError(f"escalation seed did not resume: {escalation_result}")

    return (
        clean.case_id,
        injection.case_id,
        missing.case_id,
        evidence.case_id,
        deadline.case_id,
        escalation.case_id,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.ledger.parent.mkdir(parents=True, exist_ok=True)

    # Keep the resolver server-side and case-scoped. The durable event only
    # carries revision/count metadata; this map is never serialized.
    inputs: dict[tuple[str, str], AppealInput] = {}

    def resolve(tenant_id: str, case_id: str) -> AppealInput | None:
        return inputs.get((tenant_id, case_id))

    ledger = ReceiptLedger(args.ledger)
    runtime = LocalCaseRuntime(_workflow(ledger), input_resolver=resolve)
    case_ids = _seed(runtime, inputs)
    verification = ledger.verify()
    ledger_path = args.ledger.resolve()
    report = {
        "schema_version": "0.1",
        "kind": "seeded_synthetic_demo_tenant",
        "recorded_at": NOW.isoformat().replace("+00:00", "Z"),
        "tenant_id": TENANT_ID,
        "case_count": len(case_ids),
        "case_ids": list(case_ids),
        "cases": [_snapshot(runtime, case_id) for case_id in case_ids],
        "synthetic_only": True,
        "raw_content_persisted": False,
        "hosted_follow_up_required": True,
        "board_scope_check": {
            "tenant_case_count": len(runtime.store.list_tenant(TENANT_ID)),
            "other_tenant_case_count": len(runtime.store.list_tenant("tenant-not-seeded")),
        },
        "receipt_chain": {
            "verification": "passed",
            "entry_count": verification.entry_count,
            "tip_hash": verification.tip_hash,
            "ledger_path_outside_repository": ROOT.resolve() not in ledger_path.parents,
        },
        "persistence_policy": "aggregate_case_metadata_and_reference_only_workflow_sessions",
        "limitations": [
            "The board is a local deterministic synthetic fixture, not a hosted authenticated dashboard.",
            "No real patient, payer, denial, chart, or submission data is used.",
        ],
    }

    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"\nMetadata report: {args.output}")
    print(f"Receipt ledger: {args.ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
