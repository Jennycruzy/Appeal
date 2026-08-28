"""Runnable local Appeal graph and deterministic submission gate."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from appeal_core import (
    Actor,
    ActorKind,
    Case,
    CaseState,
    CaseStateMachine,
    DecisionSource,
    EvidenceRef,
    ReceiptLedger,
    StatutoryClock,
)

from .agents import (
    ArgumentBuilderAgent,
    DeadlineSentinelAgent,
    DenialParserAgent,
    EscalationStrategistAgent,
    EvidenceMinerAgent,
    IntakeAgent,
    PolicyAnalystAgent,
    WorkflowContext,
)
from .combinator import CombinatorDecision, VetoCombinator, VetoStatus
from .models import AGENT_IDENTITIES, AppealInput, DraftPackage, WorkflowEvent, WorkflowOutcome
from .permissions import AgentPolicyRegistry, default_policy_registry
from .security import InspectionResult, InspectionStatus, LocalSecurityBoundary


LOCAL_VERSION: Final[str] = "0.1"


@dataclass(frozen=True)
class AgentGraph:
    """Inspectable local graph topology for the seven-role workflow."""

    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]

    def to_json(self) -> dict[str, object]:
        return {
            "nodes": list(self.nodes),
            "edges": [list(edge) for edge in self.edges],
            "execution_model": "deterministic_local_graph",
        }


LOCAL_AGENT_GRAPH = AgentGraph(
    nodes=(
        "intake",
        "denial_parser",
        "policy_analyst",
        "evidence_miner",
        "argument_builder",
        "deadline_sentinel",
        "escalation_strategist",
        "veto_combinator",
        "submission_gate",
    ),
    edges=(
        ("intake", "denial_parser"),
        ("denial_parser", "policy_analyst"),
        ("policy_analyst", "evidence_miner"),
        ("evidence_miner", "argument_builder"),
        ("argument_builder", "veto_combinator"),
        ("veto_combinator", "submission_gate"),
        ("submission_gate", "deadline_sentinel"),
        ("deadline_sentinel", "escalation_strategist"),
        ("escalation_strategist", "veto_combinator"),
    ),
)


@dataclass(frozen=True)
class WorkflowResult:
    outcome: WorkflowOutcome
    case_state: CaseState
    case: Case
    clock: StatutoryClock
    events: tuple[WorkflowEvent, ...]
    draft: DraftPackage | None
    combinator: CombinatorDecision | None
    failure_reason: str | None
    mutation_count: int
    context: WorkflowContext | None = field(default=None, repr=False, compare=False)

    def to_public_json(self) -> dict[str, object]:
        """Return metadata suitable for an aggregate/demo report.

        Draft prose and chart content are intentionally omitted from this
        serialization boundary. The CLI can display the in-memory draft for a
        synthetic demo without writing it to evidence or receipts.
        """

        case = self.case
        case_json = case.to_json() if hasattr(case, "to_json") else {}
        return {
            "schema_version": "0.1",
            "agent_graph": LOCAL_AGENT_GRAPH.to_json(),
            "outcome": self.outcome.value,
            "case_state": self.case_state.value,
            "case": case_json,
            "clock": self.clock.to_json(),
            "events": [
                {
                    "agent": event.agent,
                    "status": event.status,
                    "message": event.message,
                    "recorded_at": event.recorded_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                    "evidence_ref_count": len(event.evidence_refs),
                }
                for event in self.events
            ],
            "draft": (
                {
                    "claim_count": len(self.draft.claims),
                    "evidence_ref_count": len(self.draft.evidence_refs),
                    "criterion_status": self.draft.criterion_evaluation.status.value,
                    "model_dissent": self.draft.model_dissent,
                }
                if self.draft is not None
                else None
            ),
            "combinator": (
                {
                    "status": self.combinator.status.value,
                    "model_dissent": self.combinator.model_dissent,
                    "verdicts": [
                        {
                            "holder": verdict.holder,
                            "status": verdict.status.value,
                            "reason": verdict.reason,
                        }
                        for verdict in self.combinator.verdicts
                    ],
                }
                if self.combinator is not None
                else None
            ),
            "failure_reason": self.failure_reason,
            "external_mutation_count": self.mutation_count,
            "security": {
                surface: {
                    "status": inspection.status.value,
                    "provider": inspection.provider,
                    "categories": list(inspection.categories),
                }
                for surface, inspection in (
                    ("inbound", self.context.inbound_inspection if self.context is not None else None),
                    ("egress", self.context.egress_inspection if self.context is not None else None),
                    ("memory", self.context.memory_inspection if self.context is not None else None),
                )
                if inspection is not None
            },
        }


class SubmissionGate:
    """The sole local component allowed to perform the submission mutation."""

    name = "submission_gate"
    identity = "appeal-submission-gate-local-v0.1"

    def submit(
        self,
        context: WorkflowContext,
        at: datetime,
        clinician_decision: bool,
    ) -> int:
        context.require_read(self.name, "approved_draft")
        context.require_read(self.name, "clinician_signature")
        context.require_read(self.name, "veto_verdict")
        context.require_write(self.name, "external_mutation")
        if context.case.state is not CaseState.AWAITING_CLINICIAN:
            raise ValueError("submission gate requires an awaiting-clinician case")
        if context.draft is None:
            raise ValueError("submission gate requires a draft")
        if context.combinator_decision is None or not context.combinator_decision.can_submit:
            raise ValueError("submission gate requires all vetoes to be cleared")
        if not clinician_decision:
            raise ValueError("submission gate cannot submit a clinician veto")
        signature_hash = hashlib.sha256(
            f"{context.case.case_id}:{self.identity}:{at.astimezone(UTC).isoformat()}".encode("utf-8")
        ).hexdigest()
        signature = EvidenceRef(
            "ClinicianSignature",
            f"signature://{context.case.case_id}/level-1",
            signature_hash,
        )
        context.transition(
            CaseState.SUBMITTED_LEVEL_1,
            "clinician",
            at,
            "clinician co-signed the draft after the veto combinator cleared",
            context.draft.evidence_refs,
            actor_kind=ActorKind.HUMAN,
            source_kind="human",
            clinician_signature=signature,
        )
        # This is the one and only external mutation in the local workflow.
        # It is represented locally and receipt-recorded; no payer is called.
        context.record(
            self.name,
            "mutated_once",
            "single-mutation submission gate accepted the co-signed draft",
            at,
            context.draft.evidence_refs + (signature,),
            action="submission_mutation",
        )
        context.transition(
            CaseState.AWAITING_DETERMINATION,
            self.name,
            at,
            "submission recorded; awaiting payer determination",
            context.draft.evidence_refs + (signature,),
            actor_kind=ActorKind.SYSTEM,
        )
        return 1


class AppealWorkflow:
    """A local graph with seven named roles and deterministic control points."""

    def __init__(
        self,
        machine: CaseStateMachine,
        *,
        security: LocalSecurityBoundary | None = None,
        ledger: ReceiptLedger | None = None,
        policies: AgentPolicyRegistry | None = None,
    ) -> None:
        self.machine = machine
        self.security = security or LocalSecurityBoundary()
        self.ledger = ledger
        self.policies = policies or default_policy_registry()
        self.intake = IntakeAgent()
        self.denial_parser = DenialParserAgent()
        self.policy_analyst = PolicyAnalystAgent()
        self.evidence_miner = EvidenceMinerAgent()
        self.argument_builder = ArgumentBuilderAgent()
        self.deadline_sentinel = DeadlineSentinelAgent()
        self.escalation_strategist = EscalationStrategistAgent()
        self.combinator = VetoCombinator()
        self.submission_gate = SubmissionGate()

    @property
    def graph(self) -> AgentGraph:
        return LOCAL_AGENT_GRAPH

    def run(
        self,
        appeal_input: AppealInput,
        *,
        clinician_decision: bool | None = None,
        at: datetime | None = None,
    ) -> WorkflowResult:
        now = (at or appeal_input.received_at).astimezone(UTC)
        initial_actor = Actor(AGENT_IDENTITIES["intake"], ActorKind.AGENT)
        initial_source = DecisionSource("deterministic", "local-graph", LOCAL_VERSION)
        case = self.machine.create(
            appeal_input.case_id,
            appeal_input.tenant_id,
            appeal_input.received_at,
            initial_actor,
            initial_source,
        )
        context = WorkflowContext(appeal_input, self.machine, case, self.security, self.ledger, self.policies)

        self.deadline_sentinel.run(context, now)
        if context.case.state is CaseState.INTAKE_RECEIVED:
            self.intake.run(context, now)
        if context.case.state is CaseState.INTAKE_RECEIVED:
            self.denial_parser.run(context, now)
        if context.case.state is CaseState.DENIAL_PARSED:
            self.policy_analyst.run(context, now)
        if context.case.state is CaseState.CRITERION_IDENTIFIED:
            self.evidence_miner.run(context, now)
        if context.case.state is CaseState.EVIDENCE_ASSEMBLED:
            self.argument_builder.run(context, now)

        mutation_count = self._apply_clinician_gate(context, now, clinician_decision)

        if context.outcome is None:
            if context.case.state is CaseState.QUARANTINED:
                context.outcome = WorkflowOutcome.QUARANTINED
            elif context.case.state is CaseState.CLOSED_ABANDONED_DEADLINE:
                context.outcome = WorkflowOutcome.DEADLINE_ABANDONED
            elif context.case.state in {
                CaseState.PARSE_FAILED_HUMAN_REVIEW,
                CaseState.POLICY_NOT_FOUND_HUMAN_REVIEW,
                CaseState.EVIDENCE_INSUFFICIENT,
            }:
                context.outcome = WorkflowOutcome.ABSTAINED
            else:
                context.outcome = WorkflowOutcome.FAILED

        self.escalation_strategist.run(context, now)
        clock = self.deadline_sentinel.run(context, now)
        if context.case.state.value == CaseState.CLOSED_ABANDONED_DEADLINE.value:
            context.outcome = WorkflowOutcome.DEADLINE_ABANDONED
        return WorkflowResult(
            outcome=context.outcome,
            case_state=context.case.state,
            case=context.case,
            clock=clock,
            events=tuple(context.events),
            draft=context.draft,
            combinator=context.combinator_decision,
            failure_reason=context.failure_reason,
            mutation_count=mutation_count,
            context=context,
        )

    def approve(self, result: WorkflowResult, *, at: datetime) -> WorkflowResult:
        """Apply the clinician veto to an existing awaiting-clinician case."""

        context = result.context
        if context is None or result.case_state is not CaseState.AWAITING_CLINICIAN:
            raise ValueError("clinician approval requires an awaiting-clinician workflow context")
        if context.case.state is not CaseState.AWAITING_CLINICIAN:
            raise ValueError("clinician approval requires an awaiting-clinician case")
        now = at.astimezone(UTC)
        mutation_count = self._apply_clinician_gate(context, now, True)
        clock = self.deadline_sentinel.run(context, now)
        if context.case.state.value == CaseState.CLOSED_ABANDONED_DEADLINE.value:
            context.outcome = WorkflowOutcome.DEADLINE_ABANDONED
        return WorkflowResult(
            outcome=context.outcome or WorkflowOutcome.FAILED,
            case_state=context.case.state,
            case=context.case,
            clock=clock,
            events=tuple(context.events),
            draft=context.draft,
            combinator=context.combinator_decision,
            failure_reason=context.failure_reason,
            mutation_count=result.mutation_count + mutation_count,
            context=context,
        )

    def _apply_clinician_gate(
        self,
        context: WorkflowContext,
        at: datetime,
        clinician_decision: bool | None,
    ) -> int:
        if context.case.state is not CaseState.AWAITING_CLINICIAN or context.draft is None:
            return 0
        evaluation_status = context.draft.criterion_evaluation.status
        inbound = context.inbound_inspection or _clear_inspection("inbound_document")
        egress = context.egress_inspection or _clear_inspection("egress_to_zone_c")
        memory = context.memory_inspection or _clear_inspection("memory_bank")
        context.combinator_decision = self.combinator.evaluate(
            criterion_status=evaluation_status,
            evidence_floor_passed=True,
            inbound_inspection=inbound,
            egress_inspection=egress,
            memory_inspection=memory,
            clinician_decision=clinician_decision,
            model_dissent=context.draft.model_dissent,
        )
        combinator_status = context.combinator_decision.status
        context.record(
            "veto_combinator",
            combinator_status.value,
            "four independent vetoes evaluated; strictest verdict retained",
            at,
            context.draft.evidence_refs,
            receipt_outcome=("allowed" if combinator_status is not VetoStatus.BLOCKED else "refused"),
            refusal_reason=("a veto remains active" if combinator_status is VetoStatus.BLOCKED else None),
        )
        if combinator_status is VetoStatus.CLEARED:
            context.outcome = WorkflowOutcome.SUBMITTED
            return self.submission_gate.submit(context, at, True)
        if combinator_status is VetoStatus.NEEDS_HUMAN:
            context.outcome = WorkflowOutcome.AWAITING_CLINICIAN
            return 0
        context.outcome = WorkflowOutcome.VETOED
        context.failure_reason = "veto combinator retained a blocking verdict"
        return 0

    def process_determination(
        self,
        result: WorkflowResult,
        *,
        favorable: bool,
        at: datetime,
    ) -> WorkflowResult:
        """Resume a submitted case and re-derive an unfavorable escalation."""

        context = result.context
        if context is None or result.case_state is not CaseState.AWAITING_DETERMINATION:
            raise ValueError("determination processing requires a submitted workflow context")
        if context.case.state.value != CaseState.AWAITING_DETERMINATION.value:
            raise ValueError("determination processing requires a case awaiting determination")
        now = at.astimezone(UTC)
        clock = self.deadline_sentinel.run(context, now)
        if context.case.state is CaseState.CLOSED_ABANDONED_DEADLINE:
            return WorkflowResult(
                WorkflowOutcome.DEADLINE_ABANDONED,
                context.case.state,
                context.case,
                clock,
                tuple(context.events),
                context.draft,
                context.combinator_decision,
                "configured statutory clock expired",
                result.mutation_count,
                context,
            )
        refs = context.draft.evidence_refs if context.draft is not None else ()
        context.transition(
            CaseState.DETERMINATION_RECEIVED,
            "payer_adjudicator",
            now,
            "local payer determination received",
            refs,
            actor_kind=ActorKind.SYSTEM,
        )
        if favorable:
            context.transition(
                CaseState.CLOSED_WON,
                "payer_adjudicator",
                now,
                "payer determination resolved the appeal favorably",
                refs,
                actor_kind=ActorKind.SYSTEM,
            )
            return WorkflowResult(
                WorkflowOutcome.CLOSED_WON,
                context.case.state,
                context.case,
                self.deadline_sentinel.run(context, now),
                tuple(context.events),
                context.draft,
                context.combinator_decision,
                None,
                result.mutation_count,
                context,
            )
        self.escalation_strategist.run(context, now)
        escalation_draft = self.escalation_strategist.rederive_argument(context, now)
        if escalation_draft is None:
            return WorkflowResult(
                WorkflowOutcome.ABSTAINED,
                context.case.state,
                context.case,
                self.deadline_sentinel.run(context, now),
                tuple(context.events),
                context.draft,
                context.combinator_decision,
                "escalation strategy could not be re-derived",
                result.mutation_count,
                context,
            )
        return WorkflowResult(
            WorkflowOutcome.ESCALATION_READY,
            context.case.state,
            context.case,
            self.deadline_sentinel.run(context, now),
            tuple(context.events),
            escalation_draft,
            context.combinator_decision,
            None,
            result.mutation_count,
            context,
        )


def _clear_inspection(surface: str) -> InspectionResult:
    return InspectionResult(surface, InspectionStatus.CLEAR, "local_deterministic_fallback", (), "not applicable")
