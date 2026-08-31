"""Measure workflow utility from aggregate synthetic execution traces.

This is an operational benchmark, not a clinical evaluation. It derives human
actions, autonomous transitions, elapsed workflow time, mutation counts, and a
published administrative-burden reference from synthetic scenarios. It does
not infer an allowed medical amount or claim that Oregon/CMS summary data are
full Appeal cases.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from appeal_agents.demo import demo_input
from appeal_agents.workflow import AppealWorkflow
from appeal_core import ActorKind, CaseState, CaseStateMachine, DeadlineCatalog, ReceiptLedger
from appeal_platform import (
    EVIDENCE_ARRIVAL_TOPIC,
    PAYER_DETERMINATION_TOPIC,
    DomainEvent,
    LocalCaseRuntime,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
DEFAULT_OUTPUT = ROOT / "evidence" / "operational-utility-measurement.json"

AMA_BURDEN_SOURCE = (
    "https://www.ama-assn.org/about/leadership/latest-prior-authorization-survey-shows-promised-reform-remains-elusive"
)
BLS_WAGE_SOURCE = "https://www.bls.gov/news.release/archives/ocwage_04022025.htm"
OREGON_RATE_SOURCE = "evidence/oregon-evaluation.json"


def _workflow(ledger: ReceiptLedger) -> AppealWorkflow:
    deadlines = DeadlineCatalog.from_path(ROOT / "config" / "deadlines.yaml")
    return AppealWorkflow(CaseStateMachine(deadlines), ledger=ledger)


def _metric(
    scenario: str,
    runtime: LocalCaseRuntime,
    tenant_id: str,
    case_id: str,
    *,
    initial_state: CaseState,
) -> dict[str, object]:
    case = runtime.store.require(tenant_id, case_id)
    transitions = case.transitions
    human_actions = sum(transition.actor.kind is ActorKind.HUMAN for transition in transitions)
    autonomous_transitions = len(transitions) - human_actions
    mutation_count = sum(transition.to_state is CaseState.SUBMITTED_LEVEL_1 for transition in transitions)
    elapsed_hours = round(
        max(0.0, (case.last_transition.entered_at - transitions[0].entered_at).total_seconds() / 3600),
        3,
    )
    resumed = runtime.resume(tenant_id, case_id)
    assert resumed is not None
    return {
        "scenario": scenario,
        "initial_state": initial_state.value,
        "final_state": case.state.value,
        "final_outcome": resumed.workflow.outcome.value,
        "transition_count": len(transitions),
        "human_action_count": human_actions,
        "autonomous_transition_count": autonomous_transitions,
        "autonomous_transition_fraction": round(autonomous_transitions / len(transitions), 4),
        "workflow_elapsed_hours": elapsed_hours,
        "external_mutation_count": mutation_count,
        "case_fingerprint": case.fingerprint(),
    }


def _run_scenarios(ledger: ReceiptLedger) -> list[dict[str, object]]:
    metrics: list[dict[str, object]] = []

    clean = demo_input(case_id="case-demo-utility-clean", tenant_id="tenant-demo-utility")
    clean_runtime = LocalCaseRuntime(_workflow(ledger))
    clean_waiting = clean_runtime.start(clean, at=NOW)
    clean_submitted = clean_runtime.approve(clean_waiting, at=NOW + timedelta(hours=1.5))
    clean_event = DomainEvent.create(
        clean.tenant_id,
        clean.case_id,
        PAYER_DETERMINATION_TOPIC,
        f"{clean.case_id}:payer:utility-clean",
        NOW + timedelta(hours=6),
        {"decision": "favorable", "criterion_status": "satisfied", "evidence_ref_count": 2},
    )
    clean_runtime.handle_event(clean_event, at=NOW + timedelta(hours=6))
    metrics.append(
        _metric(
            "clean_win",
            clean_runtime,
            clean.tenant_id,
            clean.case_id,
            initial_state=clean_waiting.workflow.case_state,
        )
    )
    assert clean_submitted.workflow.case_state is CaseState.AWAITING_DETERMINATION

    injection = demo_input(
        injection=True,
        case_id="case-demo-utility-injection",
        tenant_id="tenant-demo-utility",
    )
    injection_runtime = LocalCaseRuntime(_workflow(ledger))
    injection_result = injection_runtime.start(injection, at=NOW)
    metrics.append(
        _metric(
            "injection_quarantine",
            injection_runtime,
            injection.tenant_id,
            injection.case_id,
            initial_state=injection_result.workflow.case_state,
        )
    )

    missing = demo_input(
        missing_evidence=True,
        case_id="case-demo-utility-missing",
        tenant_id="tenant-demo-utility",
    )
    missing_runtime = LocalCaseRuntime(_workflow(ledger))
    missing_result = missing_runtime.start(missing, at=NOW)
    metrics.append(
        _metric(
            "missing_evidence_abstention",
            missing_runtime,
            missing.tenant_id,
            missing.case_id,
            initial_state=missing_result.workflow.case_state,
        )
    )

    evidence = demo_input(
        missing_evidence=True,
        case_id="case-demo-utility-evidence",
        tenant_id="tenant-demo-utility",
    )
    evidence_runtime = LocalCaseRuntime(
        _workflow(ledger),
    )
    evidence_result = evidence_runtime.start(evidence, at=NOW)
    evidence_restart = LocalCaseRuntime(
        _workflow(ledger),
        store=evidence_runtime.store,
        spine=evidence_runtime.spine,
        session_store=evidence_runtime.session_store,
        reversibility=evidence_runtime.reversibility,
        input_resolver=lambda tenant_id, case_id: demo_input(case_id=case_id, tenant_id=tenant_id),
    )
    evidence_event = DomainEvent.create(
        evidence.tenant_id,
        evidence.case_id,
        EVIDENCE_ARRIVAL_TOPIC,
        f"{evidence.case_id}:evidence:utility-arrival",
        NOW + timedelta(hours=2),
        {"evidence_revision": "utility-arrival", "evidence_ref_count": 2},
    )
    evidence_restart.handle_event(evidence_event, at=NOW + timedelta(hours=2))
    metrics.append(
        _metric(
            "evidence_arrival_wake",
            evidence_restart,
            evidence.tenant_id,
            evidence.case_id,
            initial_state=evidence_result.workflow.case_state,
        )
    )

    deadline = demo_input(case_id="case-demo-utility-deadline", tenant_id="tenant-demo-utility")
    deadline_runtime = LocalCaseRuntime(_workflow(ledger))
    deadline_waiting = deadline_runtime.start(deadline, at=NOW)
    deadline_runtime.approve(deadline_waiting, at=NOW + timedelta(hours=1))
    deadline_runtime.sentinel_tick(at=NOW + timedelta(days=8))
    metrics.append(
        _metric(
            "deadline_abandonment",
            deadline_runtime,
            deadline.tenant_id,
            deadline.case_id,
            initial_state=deadline_waiting.workflow.case_state,
        )
    )

    escalation = demo_input(case_id="case-demo-utility-escalation", tenant_id="tenant-demo-utility")
    escalation_runtime = LocalCaseRuntime(_workflow(ledger))
    escalation_waiting = escalation_runtime.start(escalation, at=NOW)
    escalation_runtime.approve(escalation_waiting, at=NOW + timedelta(hours=1))
    escalation_event = DomainEvent.create(
        escalation.tenant_id,
        escalation.case_id,
        PAYER_DETERMINATION_TOPIC,
        f"{escalation.case_id}:payer:utility-unfavorable",
        NOW + timedelta(hours=6),
        {"decision": "unfavorable", "criterion_status": "contradicted", "evidence_ref_count": 2},
    )
    escalation_runtime.handle_event(escalation_event, at=NOW + timedelta(hours=6))
    metrics.append(
        _metric(
            "level_two_escalation",
            escalation_runtime,
            escalation.tenant_id,
            escalation.case_id,
            initial_state=escalation_waiting.workflow.case_state,
        )
    )
    return metrics


def _real_outcome_proxy() -> dict[str, object]:
    document = json.loads((ROOT / OREGON_RATE_SOURCE).read_text(encoding="utf-8"))
    counts = document["regulator_outcomes"]["counts"]
    total = sum(counts.values())
    overturns = counts.get("overturned_denial", 0) + counts.get("partial_overturn", 0)
    return {
        "source": OREGON_RATE_SOURCE,
        "scope": "official Oregon external-review outcomes; not prior-authorization and not a full Appeal corpus",
        "cases": total,
        "overturned_or_partial": overturns,
        "overturn_proxy_rate": round(overturns / total, 6) if total else None,
        "comparison_to_appeal_predictions": "not_run",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="appeal-utility-") as directory:
        ledger = ReceiptLedger(Path(directory) / "receipts.jsonl")
        scenarios = _run_scenarios(ledger)
        receipt_verification = ledger.verify()

    transition_count = sum(int(item["transition_count"]) for item in scenarios)
    autonomous_count = sum(int(item["autonomous_transition_count"]) for item in scenarios)
    report: dict[str, object] = {
        "schema_version": "0.1",
        "kind": "operational_utility_measurement",
        "recorded_at": NOW.isoformat().replace("+00:00", "Z"),
        "execution_scope": "local_deterministic_synthetic_scenarios",
        "synthetic_only": True,
        "raw_content_persisted": False,
        "scenarios": scenarios,
        "summary": {
            "case_count": len(scenarios),
            "human_action_count": sum(int(item["human_action_count"]) for item in scenarios),
            "external_mutation_count": sum(int(item["external_mutation_count"]) for item in scenarios),
            "autonomous_transition_count": autonomous_count,
            "transition_count": transition_count,
            "autonomous_transition_fraction": round(autonomous_count / transition_count, 4),
            "cases_that_refused_to_file": sum(
                int(item["external_mutation_count"]) == 0
                for item in scenarios
                if item["scenario"] in {"injection_quarantine", "missing_evidence_abstention", "deadline_abandonment"}
            ),
        },
        "published_burden_reference": {
            "source": AMA_BURDEN_SOURCE,
            "reported_requests_per_physician_week": 40,
            "reported_hours_per_physician_week": 13,
            "derived_hours_per_request": 0.325,
            "interpretation": "external administrative-burden benchmark, not measured Appeal labor",
            "wage_source": BLS_WAGE_SOURCE,
            "medical_secretary_median_hourly_usd_may_2024": 21.46,
            "derived_admin_labor_cost_per_request_usd": 6.9745,
        },
        "real_outcome_proxy": _real_outcome_proxy(),
        "recoverable_dollars": {
            "status": "sensitivity_only",
            "per_abandoned_appeal_usd": None,
            "reason": "No allowed medical amount is present in the accepted regulator-summary or external-review sources; do not invent one.",
            "formula_if_authorized_amount_is_supplied": "authorized_allowed_amount_usd * real_outcome_proxy.overturn_proxy_rate",
        },
        "receipt_chain": {
            "verification": "passed",
            "entry_count": receipt_verification.entry_count,
            "tip_hash": receipt_verification.tip_hash,
        },
        "known_limits": [
            "Synthetic traces do not measure clinical quality or regulator agreement.",
            "The Oregon rate is an external-review outcome proxy and is not a prior-authorization overturn rate.",
            "The labor benchmark is a published reference, not a case-level counterfactual.",
            "A real allowed-amount source and full Appeal evaluation remain required for a defensible recoverable-dollar claim.",
        ],
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"\nMetadata report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
