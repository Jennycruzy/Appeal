"""Local runtime joining the workflow to platform-shaped boundaries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from appeal_agents import AppealInput, AppealWorkflow, WorkflowOutcome, WorkflowResult
from appeal_agents.models import AGENT_IDENTITIES, WorkflowEvent
from appeal_core import Actor, ActorKind, CaseState, CriterionStatus, DecisionSource, ReceiptDraft

from .events import DomainEvent, LocalEventSpine
from .memory import ScopedMemoryBank
from .payer import PayerAdjudicator, PayerDecision, PayerDecisionStatus
from .reversibility import ReversibleAction, ReversibilityLedger
from .sessions import (
    LocalWorkflowSessionStore,
    WorkflowSession,
    WorkflowSessionConflict,
    WorkflowSessionStore,
)
from .store import CaseStore, CaseStoreConflict


PAYER_DETERMINATION_TOPIC = "payer.determination.received"
EVIDENCE_ARRIVAL_TOPIC = "appeal.evidence.arrived"
InputResolver = Callable[[str, str], AppealInput | None]


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
        session_store: WorkflowSessionStore | None = None,
        input_resolver: InputResolver | None = None,
    ) -> None:
        self.workflow = workflow
        self.store = store or CaseStore()
        self.spine = spine or LocalEventSpine()
        self.memory = memory or ScopedMemoryBank(workflow.security)
        self.reversibility = reversibility or ReversibilityLedger()
        self.session_store = session_store or LocalWorkflowSessionStore()
        self.input_resolver = input_resolver
        self._inputs: dict[tuple[str, str], AppealInput] = {}

    def start(
        self,
        appeal_input: AppealInput,
        *,
        clinician_decision: bool | None = None,
        at: datetime | None = None,
    ) -> RuntimeResult:
        self._inputs[(appeal_input.tenant_id, appeal_input.case_id)] = appeal_input
        result = self.workflow.run(appeal_input, clinician_decision=clinician_decision, at=at)
        runtime_result = RuntimeResult(result)
        self._persist(runtime_result)
        return runtime_result

    def resume(self, tenant_id: str, case_id: str) -> RuntimeResult | None:
        """Rehydrate a safe workflow context for a persisted case."""

        case = self.store.get(tenant_id, case_id)
        if case is None:
            return None
        session = self.session_store.get(tenant_id, case_id)
        if session is None:
            return None
        restored = session.to_runtime_result(self.workflow, case)
        return RuntimeResult(restored.workflow, restored.payer_decision)

    def handle_event(
        self,
        event: DomainEvent,
        *,
        at: datetime | None = None,
    ) -> dict[str, object]:
        """Resume one persisted case from a reference-only external event.

        The case state and session fingerprints are the idempotency boundary:
        a duplicate event observes the already-advanced state and cannot
        create another transition or mutation. Event payloads contain only
        bounded metadata; evidence bodies are resolved server-side.
        """

        now = (at or event.published_at).astimezone(UTC)
        if event.topic not in {PAYER_DETERMINATION_TOPIC, EVIDENCE_ARRIVAL_TOPIC}:
            return {
                "status": "ignored",
                "event_id": event.event_id,
                "reason": "event_topic_not_workflow_resumable",
            }
        current = self.resume(event.tenant_id, event.case_id)
        if current is None:
            return {
                "status": "skipped",
                "event_id": event.event_id,
                "reason": "case_or_workflow_session_not_found",
            }
        if current.workflow.context is not None and event.event_id in current.workflow.context.processed_event_ids:
            return {
                "status": "duplicate",
                "event_id": event.event_id,
                "reason": "event was already processed",
                "case_state": current.workflow.case.state.value,
            }
        if event.topic == PAYER_DETERMINATION_TOPIC:
            return self._handle_payer_event(current, event, now)
        return self._handle_evidence_event(current, event, now)

    def _handle_payer_event(
        self,
        current: RuntimeResult,
        event: DomainEvent,
        at: datetime,
    ) -> dict[str, object]:
        payload = event.payload_dict()
        decision = payload.get("decision")
        if decision not in {
            PayerDecisionStatus.FAVORABLE.value,
            PayerDecisionStatus.UNFAVORABLE.value,
            PayerDecisionStatus.PENDED.value,
        }:
            raise ValueError("payer determination event has an unsupported decision")
        criterion_status = payload.get("criterion_status")
        if criterion_status not in {status.value for status in CriterionStatus}:
            raise ValueError("payer determination event has an unsupported criterion_status")
        evidence_ref_count = payload.get("evidence_ref_count")
        if (
            not isinstance(evidence_ref_count, int)
            or isinstance(evidence_ref_count, bool)
            or evidence_ref_count < 0
        ):
            raise ValueError("payer determination event requires a non-negative evidence_ref_count")
        if decision == PayerDecisionStatus.FAVORABLE.value and (
            criterion_status != CriterionStatus.SATISFIED.value or evidence_ref_count < 1
        ):
            raise ValueError("favorable payer determination must carry satisfied evidence metadata")
        if decision == PayerDecisionStatus.UNFAVORABLE.value and criterion_status != CriterionStatus.CONTRADICTED.value:
            raise ValueError("unfavorable payer determination must carry contradicted criterion metadata")
        if decision == PayerDecisionStatus.PENDED.value and criterion_status not in {
            CriterionStatus.ABSENT.value,
            CriterionStatus.CONFLICTED.value,
        }:
            raise ValueError("pended payer determination must carry absent or conflicted criterion metadata")
        if decision == PayerDecisionStatus.PENDED.value:
            if current.workflow.context is not None:
                current.workflow.context.processed_event_ids.add(event.event_id)
            payer_decision = _payer_decision_from_event(current, decision, criterion_status)
            self._persist(
                RuntimeResult(current.workflow, payer_decision),
                expected_fingerprint=current.workflow.case.fingerprint(),
            )
            return {
                "status": "ignored",
                "event_id": event.event_id,
                "reason": "payer determination is still pending",
                "case_state": current.workflow.case.state.value,
                "payer_decision": payer_decision.to_json(),
            }
        if current.workflow.case.state is not CaseState.AWAITING_DETERMINATION:
            return {
                "status": "duplicate",
                "event_id": event.event_id,
                "reason": "case is no longer awaiting payer determination",
                "case_state": current.workflow.case.state.value,
            }
        resumed = self.workflow.process_determination(
            current.workflow,
            favorable=decision == PayerDecisionStatus.FAVORABLE.value,
            at=at,
        )
        if resumed.context is not None:
            resumed.context.processed_event_ids.add(event.event_id)
        payer_decision = _payer_decision_from_event(current, decision, criterion_status)
        result = RuntimeResult(resumed, payer_decision)
        self._persist(result, expected_fingerprint=current.workflow.case.fingerprint())
        return _event_result(event, result, "payer_determination_resumed")

    def _handle_evidence_event(
        self,
        current: RuntimeResult,
        event: DomainEvent,
        at: datetime,
    ) -> dict[str, object]:
        payload = event.payload_dict()
        revision = payload.get("evidence_revision")
        count = payload.get("evidence_ref_count")
        if not isinstance(revision, str) or not revision.strip():
            raise ValueError("evidence event requires evidence_revision metadata")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError("evidence event requires a positive evidence_ref_count")
        if current.workflow.case.state is not CaseState.EVIDENCE_INSUFFICIENT:
            return {
                "status": "duplicate",
                "event_id": event.event_id,
                "reason": "case is not waiting for evidence",
                "case_state": current.workflow.case.state.value,
            }
        appeal_input = self._resolve_input(event.tenant_id, event.case_id)
        if appeal_input is None:
            return {
                "status": "skipped",
                "event_id": event.event_id,
                "reason": "authorized_case_input_not_available",
            }
        resumed = self.workflow.resume_after_evidence(current.workflow, appeal_input, at=at)
        if resumed.context is not None:
            resumed.context.processed_event_ids.add(event.event_id)
        result = RuntimeResult(resumed, current.payer_decision)
        self._persist(result, expected_fingerprint=current.workflow.case.fingerprint())
        return _event_result(event, result, "evidence_arrival_resumed")

    def _resolve_input(self, tenant_id: str, case_id: str) -> AppealInput | None:
        local = self._inputs.get((tenant_id, case_id))
        if local is not None:
            return local
        if self.input_resolver is None:
            return None
        resolved = self.input_resolver(tenant_id, case_id)
        if resolved is not None:
            self._inputs[(tenant_id, case_id)] = resolved
        return resolved

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
        runtime_result = RuntimeResult(resumed, payer_decision)
        self._persist(runtime_result, expected_fingerprint=result.workflow.case.fingerprint())
        return runtime_result

    def approve(self, result: RuntimeResult, *, at: datetime) -> RuntimeResult:
        """Resume an awaiting-clinician case through the human co-signature."""

        approved = self.workflow.approve(result.workflow, at=at)
        runtime_result = RuntimeResult(approved)
        self._persist(runtime_result, expected_fingerprint=result.workflow.case.fingerprint())
        return runtime_result

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
            session = self.session_store.get(case.tenant_id, case.case_id)
            if session is not None:
                try:
                    self.session_store.save(
                        replace(
                            session,
                            case_fingerprint=updated.fingerprint(),
                            events=session.events
                            + (
                                WorkflowEvent(
                                    "deadline_sentinel",
                                    "expired",
                                    reason,
                                    now,
                                    case.last_transition.evidence_refs,
                                ),
                            ),
                            outcome=WorkflowOutcome.DEADLINE_ABANDONED,
                            failure_reason=reason,
                        ),
                        expected_fingerprint=case.fingerprint(),
                    )
                except WorkflowSessionConflict:
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

    def _persist(self, result: RuntimeResult, *, expected_fingerprint: str | None = None) -> None:
        workflow_result = result.workflow
        self.store.save(workflow_result.case, expected_fingerprint=expected_fingerprint)
        for index, event in enumerate(workflow_result.events, start=1):
            self.spine.publish(
                DomainEvent.create(
                    workflow_result.case.tenant_id,
                    workflow_result.case.case_id,
                    "appeal.workflow.event",
                    f"{workflow_result.case.case_id}:workflow-event:{index}",
                    event.recorded_at,
                    {
                        "agent": event.agent,
                        "status": event.status,
                        "evidence_ref_count": len(event.evidence_refs),
                    },
                )
            )
        self.memory.write(
            workflow_result.case.tenant_id,
            workflow_result.case.case_id,
            "local_case_runtime",
            "workflow_status",
            f"outcome={workflow_result.outcome.value};state={workflow_result.case.state.value};events={len(workflow_result.events)}",
            workflow_result.case.entered_at,
        )
        if workflow_result.context is not None:
            self.session_store.save(
                WorkflowSession.from_result(workflow_result, result.payer_decision),
                expected_fingerprint=expected_fingerprint,
            )
        if workflow_result.mutation_count:
            submission_transition = next(
                transition
                for transition in workflow_result.case.transitions
                if transition.to_state is CaseState.SUBMITTED_LEVEL_1
            )
            self.reversibility.record_action(
                ReversibleAction(
                    action_id=f"{workflow_result.case.case_id}:submission:level-1",
                    tenant_id=workflow_result.case.tenant_id,
                    case_id=workflow_result.case.case_id,
                    action_kind="submit_level_1",
                    idempotency_key=f"{workflow_result.case.case_id}:submission:level-1",
                    performed_at=submission_transition.entered_at,
                    external_reference=f"submission://{workflow_result.case.case_id}/level-1",
                    compensating_action="withdraw_level_1_submission",
                )
            )


def _event_result(event: DomainEvent, result: RuntimeResult, action: str) -> dict[str, object]:
    response: dict[str, object] = {
        "status": "resumed",
        "event_id": event.event_id,
        "action": action,
        "case_state": result.workflow.case.state.value,
        "outcome": result.workflow.outcome.value,
        "mutation_count": result.workflow.mutation_count,
    }
    if result.payer_decision is not None:
        response["payer_decision"] = result.payer_decision.to_json()
    return response


def _payer_decision_from_event(
    current: RuntimeResult,
    decision: str,
    criterion_status: str,
) -> PayerDecision:
    context = current.workflow.context
    if context is None or context.input.policy is None:
        raise ValueError("payer determination requires the persisted policy criterion")
    evaluation_refs = context.criterion_evaluation.evidence_refs if context.criterion_evaluation is not None else ()
    return PayerDecision(
        case_id=current.workflow.case.case_id,
        tenant_id=current.workflow.case.tenant_id,
        status=PayerDecisionStatus(decision),
        criterion_id=context.input.policy.criterion_id,
        criterion_status=CriterionStatus(criterion_status),
        reason="payer determination received through the typed event boundary",
        evidence_refs=evaluation_refs,
        payer_graph_fingerprint=context.input.policy.fingerprint(),
    )
