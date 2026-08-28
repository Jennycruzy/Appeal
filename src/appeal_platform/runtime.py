"""Local runtime joining the workflow to platform-shaped boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from appeal_agents import AppealInput, AppealWorkflow, WorkflowOutcome, WorkflowResult
from appeal_core import Actor, ActorKind, CaseState, DecisionSource, ReceiptDraft
from appeal_agents.models import AGENT_IDENTITIES

from .events import DomainEvent, LocalEventSpine
from .memory import ScopedMemoryBank
from .payer import PayerAdjudicator, PayerDecision, PayerDecisionStatus
from .reversibility import ReversibleAction, ReversibilityLedger
from .store import CaseStore, CaseStoreConflict


@dataclass(frozen=True)
class RuntimeResult:
    workflow: WorkflowResult
    payer_decision: PayerDecision | None = None

    def to_public_json(self) -> dict[str, object]:
        result = self.workflow.to_public_json()
        if self.payer_decision is not None:
            result["payer_decision"] = self.payer_decision.to_json()
        return result


@dataclass(frozen=True)
class SentinelTickResult:
    inspected_count: int
    expired_count: int
    abandoned_count: int
    skipped_non_executable_count: int
    conflict_count: int
    updated_cases: tuple[tuple[str, str], ...] = ()

    def to_public_json(self) -> dict[str, object]:
        return {
            "inspected_count": self.inspected_count,
            "expired_count": self.expired_count,
            "abandoned_count": self.abandoned_count,
            "skipped_non_executable_count": self.skipped_non_executable_count,
            "conflict_count": self.conflict_count,
        }


class LocalCaseRuntime:
    """An event-driven local boundary around the deterministic agent graph."""

    def __init__(
        self,
        workflow: AppealWorkflow,
        *,
        store: CaseStore | None = None,
        spine: LocalEventSpine | None = None,
        memory: ScopedMemoryBank | None = None,
        reversibility: ReversibilityLedger | None = None,
    ) -> None:
        self.workflow = workflow
        self.store = store or CaseStore()
        self.spine = spine or LocalEventSpine()
        self.memory = memory or ScopedMemoryBank(workflow.security)
        self.reversibility = reversibility or ReversibilityLedger()

    def start(
        self,
        appeal_input: AppealInput,
        *,
        clinician_decision: bool | None = None,
        at: datetime | None = None,
    ) -> RuntimeResult:
        result = self.workflow.run(appeal_input, clinician_decision=clinician_decision, at=at)
        self._persist(result)
        return RuntimeResult(result)

    def submit_and_adjudicate(
        self,
        appeal_input: AppealInput,
        payer: PayerAdjudicator,
        *,
        at: datetime | None = None,
    ) -> RuntimeResult:
        submitted = self.start(appeal_input, clinician_decision=True, at=at)
        return self.adjudicate(submitted, payer, at=at)

    def adjudicate(
        self,
        result: RuntimeResult,
        payer: PayerAdjudicator,
        *,
        at: datetime | None = None,
    ) -> RuntimeResult:
        if result.workflow.outcome is not WorkflowOutcome.SUBMITTED or result.workflow.context is None:
            return result
        appeal_input = result.workflow.context.input
        context = result.workflow.context
        payer_decision = payer.adjudicate(
            appeal_input.case_id,
            appeal_input.tenant_id,
            context.observations,
        )
        decision_at = (at or appeal_input.received_at).astimezone(UTC)
        self.spine.publish(
            DomainEvent.create(
                appeal_input.tenant_id,
                appeal_input.case_id,
                "payer.determination.received",
                f"{appeal_input.case_id}:payer-determination:1",
                decision_at,
                {
                    "decision": payer_decision.status.value,
                    "criterion_status": payer_decision.criterion_status.value,
                    "evidence_ref_count": len(payer_decision.evidence_refs),
                },
            )
        )
        resumed = self.workflow.process_determination(
            result.workflow,
            favorable=payer_decision.status is PayerDecisionStatus.FAVORABLE,
            at=decision_at,
        )
        self._persist(resumed, expected_fingerprint=result.workflow.case.fingerprint())
        return RuntimeResult(resumed, payer_decision)

    def approve(self, result: RuntimeResult, *, at: datetime) -> RuntimeResult:
        """Resume an awaiting-clinician case through the human co-signature."""

        approved = self.workflow.approve(result.workflow, at=at)
        self._persist(approved, expected_fingerprint=result.workflow.case.fingerprint())
        return RuntimeResult(approved)

    def sentinel_tick(self, *, at: datetime | None = None) -> SentinelTickResult:
        """Process expired persisted cases without requiring workflow content."""

        now = (at or datetime.now(UTC)).astimezone(UTC)
        inspected = 0
        expired = 0
        abandoned = 0
        skipped_non_executable = 0
        conflicts = 0
        updated_cases: list[tuple[str, str]] = []
        actor = Actor(AGENT_IDENTITIES["deadline_sentinel"], ActorKind.SCHEDULER)
        source = DecisionSource("deterministic", "deadline-sentinel", "0.1")

        for case in self.store.list_all():
            inspected += 1
            clock = self.workflow.machine.statutory_clock(case)
            if clock.status.value != "verified":
                skipped_non_executable += 1
                continue
            if not clock.is_expired(now):
                continue
            expired += 1
            if case.state not in {
                CaseState.AWAITING_DETERMINATION,
                CaseState.ESCALATION_ELIGIBLE,
                CaseState.PEER_TO_PEER_REQUESTED,
                CaseState.EXTERNAL_REVIEW_FILED,
            }:
                continue
            reason = "statutory clock expired; case abandoned without a late action"
            idempotency_key = f"{case.case_id}:deadline-expired:{case.deadline_key}"
            updated = self.workflow.machine.transition(
                case,
                CaseState.CLOSED_ABANDONED_DEADLINE,
                now,
                actor,
                source,
                reason,
                case.last_transition.evidence_refs,
                idempotency_key,
            )
            try:
                self.store.save(updated, expected_fingerprint=case.fingerprint())
            except CaseStoreConflict:
                conflicts += 1
                continue
            abandoned += 1
            updated_cases.append((case.tenant_id, case.case_id))
            if self.workflow.ledger is not None:
                self.workflow.ledger.append(
                    ReceiptDraft(
                        receipt_id=idempotency_key,
                        recorded_at=now,
                        tenant_id=case.tenant_id,
                        case_id=case.case_id,
                        actor=actor,
                        action="deadline_expiration",
                        decision_source=source,
                        evidence_refs=case.last_transition.evidence_refs,
                        outcome="allowed",
                        reason=reason,
                        idempotency_key=idempotency_key,
                    )
                )
            self.spine.publish(
                DomainEvent.create(
                    case.tenant_id,
                    case.case_id,
                    "deadline.sentinel.expired",
                    idempotency_key,
                    now,
                    {"from_state": case.state.value, "to_state": updated.state.value},
                )
            )
        return SentinelTickResult(
            inspected,
            expired,
            abandoned,
            skipped_non_executable,
            conflicts,
            tuple(updated_cases),
        )

    def _persist(self, result: WorkflowResult, *, expected_fingerprint: str | None = None) -> None:
        self.store.save(result.case, expected_fingerprint=expected_fingerprint)
        for index, event in enumerate(result.events, start=1):
            self.spine.publish(
                DomainEvent.create(
                    result.case.tenant_id,
                    result.case.case_id,
                    "appeal.workflow.event",
                    f"{result.case.case_id}:workflow-event:{index}",
                    event.recorded_at,
                    {
                        "agent": event.agent,
                        "status": event.status,
                        "evidence_ref_count": len(event.evidence_refs),
                    },
                )
            )
        self.memory.write(
            result.case.tenant_id,
            result.case.case_id,
            "local_case_runtime",
            "workflow_status",
            f"outcome={result.outcome.value};state={result.case.state.value};events={len(result.events)}",
            result.case.entered_at,
        )
        if result.mutation_count:
            submission_transition = next(
                transition
                for transition in result.case.transitions
                if transition.to_state is CaseState.SUBMITTED_LEVEL_1
            )
            self.reversibility.record_action(
                ReversibleAction(
                    action_id=f"{result.case.case_id}:submission:level-1",
                    tenant_id=result.case.tenant_id,
                    case_id=result.case.case_id,
                    action_kind="submit_level_1",
                    idempotency_key=f"{result.case.case_id}:submission:level-1",
                    performed_at=submission_transition.entered_at,
                    external_reference=f"submission://{result.case.case_id}/level-1",
                    compensating_action="withdraw_level_1_submission",
                )
            )
