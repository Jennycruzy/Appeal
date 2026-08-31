"""The seven local Appeal agents.

Each role has a narrow input contract. The classes are deliberately
deterministic so the workflow can be tested without a model or cloud account;
model-backed implementations can later satisfy the same contracts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, cast

from appeal_core import (
    Actor,
    ActorKind,
    Case,
    CaseState,
    CaseStateMachine,
    CriterionEvaluation,
    CriterionStatus,
    DecisionSource,
    DraftClaim,
    EvidenceDisposition,
    EvidenceObservation,
    EvidenceRef,
    EvidenceFloorViolation,
    PolicyCriterion,
    ReceiptDraft,
    ReceiptLedger,
    SourceSpan,
    StatutoryClock,
    UnverifiedDeadline,
    evaluate_criterion,
    validate_claims,
)
from appeal_core.ledger import ReceiptOutcome
from appeal_core.state_machine import ALLOWED_TRANSITIONS, DecisionKind

from .combinator import CombinatorDecision, VetoCombinator
from .models import (
    AGENT_IDENTITIES,
    AppealInput,
    DenialParse,
    DenialDocument,
    DraftPackage,
    PolicyMatch,
    WorkflowEvent,
    WorkflowOutcome,
)
from .permissions import AgentPolicyRegistry
from .security import InspectionResult, InspectionStatus, LocalSecurityBoundary


_REQUEST_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"requested\s+(?:service|item|drug)\s*:\s*([^.;\n]+)", re.IGNORECASE
)
_REASON_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"reason\s*:\s*([^.;\n]+)", re.IGNORECASE
)
_DIAGNOSIS_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"diagnosis\s*:\s*([^.;\n]+)", re.IGNORECASE
)
_POLICY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"policy\s+(?:reference|section)\s*:\s*([A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)\b", re.IGNORECASE
)


def _leaf_nodes(node: PolicyCriterion) -> tuple[PolicyCriterion, ...]:
    if node.logic.value == "LEAF":
        return (node,)
    result: list[PolicyCriterion] = []
    for child in node.children:
        result.extend(_leaf_nodes(child))
    return tuple(result)


def _span(document_hash: str, content: str, match: re.Match[str]) -> SourceSpan:
    start, end = match.span(0)
    return SourceSpan(document_hash, start, end, content[start:end])


@dataclass
class WorkflowContext:
    """Mutable in-process context; only references enter the receipt ledger."""

    input: AppealInput
    machine: CaseStateMachine
    case: Case
    security: LocalSecurityBoundary
    ledger: ReceiptLedger | None = None
    policies: AgentPolicyRegistry | None = None
    inbound_inspection: InspectionResult | None = None
    egress_inspection: InspectionResult | None = None
    memory_inspection: InspectionResult | None = None
    denial_parse: DenialParse | None = None
    policy_match: PolicyMatch | None = None
    observations: tuple[EvidenceObservation, ...] = ()
    criterion_evaluation: CriterionEvaluation | None = None
    draft: DraftPackage | None = None
    combinator_decision: CombinatorDecision | None = None
    events: list[WorkflowEvent] = field(default_factory=list)
    outcome: WorkflowOutcome | None = None
    failure_reason: str | None = None
    # A one-way binding used when a durable session is rehydrated. The raw
    # patient identifier remains in the transient input only.
    patient_scope_hash: str | None = None
    # Event IDs are bounded transport metadata, not event bodies. They make a
    # no-progress retry (for example, still-missing evidence) idempotent.
    processed_event_ids: set[str] = field(default_factory=set)

    def require_read(self, agent_name: str, scope: str) -> None:
        if self.policies is not None:
            self.policies.for_role(agent_name).require_read(scope)

    def require_write(self, agent_name: str, scope: str) -> None:
        if self.policies is not None:
            self.policies.for_role(agent_name).require_write(scope)

    def require_patient_scope(self, agent_name: str, requested_patient_id: str) -> None:
        if self.policies is not None:
            self.policies.for_role(agent_name).require_patient_scope(requested_patient_id, self.input.patient_id)

    def _actor(self, agent_name: str, kind: ActorKind = ActorKind.AGENT) -> Actor:
        identity = AGENT_IDENTITIES.get(agent_name, f"appeal-{agent_name}-local-v0.1")
        return Actor(identity, kind)

    def _source(self, agent_name: str, kind: DecisionKind = "deterministic") -> DecisionSource:
        return DecisionSource(kind, f"{agent_name}-local", "0.1")

    def record(
        self,
        agent_name: str,
        status: str,
        message: str,
        at: datetime,
        evidence_refs: tuple[EvidenceRef, ...] = (),
        *,
        receipt_outcome: str = "allowed",
        refusal_reason: str | None = None,
        actor_kind: ActorKind = ActorKind.AGENT,
        action: str | None = None,
    ) -> None:
        at = at.astimezone(UTC)
        event = WorkflowEvent(agent_name, status, message, at, evidence_refs)
        self.events.append(event)
        if self.ledger is None:
            return
        event_number = len(self.events)
        self.ledger.append(
            ReceiptDraft(
                receipt_id=f"{self.case.case_id}:event:{event_number}",
                recorded_at=at,
                tenant_id=self.case.tenant_id,
                case_id=self.case.case_id,
                actor=self._actor(agent_name, actor_kind),
                action=action or f"agent_event:{agent_name}",
                decision_source=self._source(agent_name),
                evidence_refs=evidence_refs,
                outcome=cast(ReceiptOutcome, receipt_outcome),
                reason=message,
                idempotency_key=f"{self.case.case_id}:event:{event_number}",
                refusal_reason=refusal_reason,
            )
        )

    def transition(
        self,
        to_state: CaseState,
        agent_name: str,
        at: datetime,
        reason: str,
        evidence_refs: tuple[EvidenceRef, ...] = (),
        *,
        actor_kind: ActorKind = ActorKind.AGENT,
        source_kind: DecisionKind = "deterministic",
        clinician_signature: EvidenceRef | None = None,
    ) -> None:
        self.case = self.machine.transition(
            self.case,
            to_state,
            at,
            self._actor(agent_name, actor_kind),
            self._source(agent_name, source_kind),
            reason,
            evidence_refs,
            f"{self.case.case_id}:state:{len(self.case.transitions)}:{to_state.value}",
            clinician_signature,
        )
        self.record(agent_name, "state_transition", f"entered {to_state.value}", at, evidence_refs, actor_kind=actor_kind)


class IntakeAgent:
    name = "intake"

    def run(self, context: WorkflowContext, at: datetime) -> None:
        context.require_read(self.name, "untrusted_denial")
        context.require_read(self.name, "security_boundary")
        context.require_write(self.name, "case_state")
        result = context.security.inspect_inbound(context.input.denial.content)
        context.inbound_inspection = result
        if context.input.denial.multimodal_required:
            context.record(
                self.name,
                "fallback",
                "multimodal document marked for vision extraction; local text adapter used",
                at,
            )
        if result.status is InspectionStatus.BLOCKED:
            context.outcome = WorkflowOutcome.QUARANTINED
            context.failure_reason = result.reason
            context.transition(
                CaseState.QUARANTINED,
                self.name,
                at,
                "inbound safety inspection blocked the untrusted document",
                receipt_outcome_refs(context.input.denial),
            )
            context.record(
                self.name,
                "blocked",
                "case quarantined after inbound safety inspection",
                at,
                receipt_outcome_refs(context.input.denial),
                receipt_outcome="refused",
                refusal_reason="prompt injection indicators detected",
            )
            return
        context.record(self.name, "clear", "inbound safety inspection passed", at)


def receipt_outcome_refs(document: DenialDocument) -> tuple[EvidenceRef, ...]:
    return (EvidenceRef("DenialDocument", document.uri, document.source_hash),)


class DenialParserAgent:
    name = "denial_parser"

    def run(self, context: WorkflowContext, at: datetime) -> None:
        if context.case.state is not CaseState.INTAKE_RECEIVED:
            return
        context.require_read(self.name, "denial_reference")
        context.require_read(self.name, "security_boundary")
        context.require_write(self.name, "case_state")
        document = context.input.denial
        matches = {
            "requested": _REQUEST_PATTERN.search(document.content),
            "reason": _REASON_PATTERN.search(document.content),
            "diagnosis": _DIAGNOSIS_PATTERN.search(document.content),
            "policy": _POLICY_PATTERN.search(document.content),
        }
        if any(match is None for match in matches.values()):
            context.outcome = WorkflowOutcome.ABSTAINED
            context.failure_reason = "denial parser could not establish all required structured fields"
            context.transition(
                CaseState.PARSE_FAILED_HUMAN_REVIEW,
                self.name,
                at,
                "required denial fields were not established",
                receipt_outcome_refs(document),
            )
            context.record(
                self.name,
                "abstained",
                "denial parsing stopped for human review",
                at,
                receipt_outcome_refs(document),
                receipt_outcome="refused",
                refusal_reason="required denial fields missing",
            )
            return
        requested = matches["requested"]
        reason = matches["reason"]
        diagnosis = matches["diagnosis"]
        policy = matches["policy"]
        assert requested is not None
        assert reason is not None
        assert diagnosis is not None
        assert policy is not None
        reason_text = reason.group(1).strip()
        reason_code = "medical_necessity" if "medical" in reason_text.lower() else "coverage_denial"
        context.denial_parse = DenialParse(
            requested_item=requested.group(1).strip(),
            reason_code=reason_code,
            diagnosis=diagnosis.group(1).strip(),
            policy_reference=policy.group(1).strip(),
            spans=tuple(
                _span(document.source_hash, document.content, match)
                for match in (requested, reason, diagnosis, policy)
            ),
        )
        context.transition(CaseState.DENIAL_PARSED, self.name, at, "denial fields parsed with source spans", receipt_outcome_refs(document))


class PolicyAnalystAgent:
    name = "policy_analyst"

    def run(self, context: WorkflowContext, at: datetime) -> None:
        if context.case.state is not CaseState.DENIAL_PARSED:
            return
        context.require_read(self.name, "policy_corpus")
        context.require_read(self.name, "denial_reference")
        context.require_write(self.name, "case_state")
        policy = context.input.policy
        parsed = context.denial_parse
        if policy is None or parsed is None or parsed.policy_reference != policy.policy_id:
            context.outcome = WorkflowOutcome.ABSTAINED
            context.failure_reason = "the denial policy reference could not be matched to a versioned criterion"
            context.transition(
                CaseState.POLICY_NOT_FOUND_HUMAN_REVIEW,
                self.name,
                at,
                "policy reference did not match an available policy criterion",
            )
            context.record(
                self.name,
                "abstained",
                "policy location stopped for human review",
                at,
                receipt_outcome="refused",
                refusal_reason="policy criterion unavailable or mismatched",
            )
            return
        context.policy_match = PolicyMatch(policy.policy_id, policy.criterion_id, policy, policy.source_span)
        policy_ref = EvidenceRef(
            "PolicyClause",
            f"policy://{policy.policy_id}/{policy.criterion_id}",
            policy.source_span.source_hash,
        )
        context.transition(
            CaseState.POLICY_LOCATED,
            self.name,
            at,
            "matched denial reference to versioned policy criterion",
            (policy_ref,),
        )
        context.transition(CaseState.CRITERION_IDENTIFIED, self.name, at, "selected the policy criterion tree for evaluation")


class EvidenceMinerAgent:
    name = "evidence_miner"

    def run(self, context: WorkflowContext, at: datetime) -> None:
        if context.case.state not in {CaseState.CRITERION_IDENTIFIED, CaseState.EVIDENCE_INSUFFICIENT} or context.policy_match is None:
            return
        context.require_read(self.name, "scoped_fhir_chart")
        context.require_read(self.name, "case_metadata")
        context.require_write(self.name, "surfaced_evidence")
        context.require_write(self.name, "case_state")
        patient_id = context.input.patient_id
        context.require_patient_scope(self.name, patient_id)
        if any(resource.patient_id != patient_id for resource in context.input.chart):
            context.outcome = WorkflowOutcome.QUARANTINED
            context.failure_reason = "evidence access scope violation"
            context.transition(CaseState.QUARANTINED, self.name, at, "chart scope violation detected")
            context.record(
                self.name,
                "blocked",
                "case quarantined after chart scope violation",
                at,
                receipt_outcome="refused",
                refusal_reason="Evidence Miner attempted cross-patient access",
            )
            return
        observations: list[EvidenceObservation] = []
        for leaf in _leaf_nodes(context.policy_match.criterion):
            criterion_id = leaf.criterion_id
            accepted_types = set(leaf.satisfied_by)
            matches = tuple(resource for resource in context.input.chart if resource.resource_type in accepted_types)
            if matches:
                references = tuple(resource.evidence_ref(context.case.case_id) for resource in matches)
                observations.append(
                    EvidenceObservation(
                        observation_id=f"obs.{criterion_id}",
                        leaf_criterion_id=criterion_id,
                        disposition=EvidenceDisposition.SATISFIED,
                        evidence_type=matches[0].resource_type,
                        references=references,
                    )
                )
            else:
                evidence_type = next(iter(accepted_types), "FHIR.Resource")
                observations.append(
                    EvidenceObservation(
                        observation_id=f"obs.{criterion_id}",
                        leaf_criterion_id=criterion_id,
                        disposition=EvidenceDisposition.ABSENT,
                        evidence_type=evidence_type,
                        references=(),
                    )
                )
        context.observations = tuple(observations)
        context.criterion_evaluation = evaluate_criterion(context.policy_match.criterion, context.observations)
        refs = tuple(ref for observation in observations for ref in observation.references)
        retrying_after_missing_evidence = context.case.state is CaseState.EVIDENCE_INSUFFICIENT
        if context.criterion_evaluation.status is CriterionStatus.SATISFIED:
            context.transition(CaseState.EVIDENCE_ASSEMBLED, self.name, at, "required evidence surfaced for every criterion branch", refs)
            context.record(self.name, "complete", "Evidence Miner returned scoped FHIR references", at, refs)
        else:
            if not retrying_after_missing_evidence:
                context.transition(CaseState.EVIDENCE_INSUFFICIENT, self.name, at, "Evidence Floor cannot establish the criterion", refs)
            context.outcome = WorkflowOutcome.ABSTAINED
            context.failure_reason = "required clinical evidence is absent or contradictory"
            context.record(
                self.name,
                "abstained",
                "Evidence Miner declined to support an unsupported criterion",
                at,
                refs,
                receipt_outcome="refused",
                refusal_reason="criterion evidence is not satisfied",
            )


class ArgumentBuilderAgent:
    name = "argument_builder"

    def run(self, context: WorkflowContext, at: datetime) -> None:
        if context.case.state is not CaseState.EVIDENCE_ASSEMBLED:
            return
        context.require_read(self.name, "surfaced_evidence")
        context.require_read(self.name, "policy_clause")
        context.require_read(self.name, "case_memory")
        context.require_write(self.name, "draft")
        context.require_write(self.name, "case_state")
        match = context.policy_match
        evaluation = context.criterion_evaluation
        if match is None or evaluation is None:
            context.outcome = WorkflowOutcome.FAILED
            context.failure_reason = "argument builder lacked policy or criterion evaluation"
            return
        observation_ids = tuple(
            observation.observation_id
            for observation in context.observations
            if observation.disposition is EvidenceDisposition.SATISFIED
        )
        claims = (
            DraftClaim(
                claim_id="claim.criterion-supported",
                criterion_id=match.criterion.criterion_id,
                text="The surfaced chart evidence satisfies the identified policy criterion.",
                kind="supported",
                observation_ids=observation_ids,
            ),
        )
        try:
            validate_claims(match.criterion, evaluation, context.observations, claims)
        except EvidenceFloorViolation as error:
            context.outcome = WorkflowOutcome.ABSTAINED
            context.failure_reason = str(error)
            context.record(
                self.name,
                "abstained",
                "draft rejected by the deterministic Evidence Floor",
                at,
                receipt_outcome="refused",
                refusal_reason="draft claim could not be proven",
            )
            return
        policy_ref = EvidenceRef(
            "PolicyClause",
            f"policy://{match.policy_id}/{match.criterion_id}",
            match.source_span.source_hash,
        )
        refs = (policy_ref,) + tuple(ref for observation in context.observations for ref in observation.references)
        text = (
            "Appeal argument: the requested service is supported by the identified "
            "policy criterion. Every clinical assertion in this draft resolves to "
            "a surfaced FHIR reference; the policy assertion resolves to the cited "
            "criterion span."
        )
        context.draft = DraftPackage(text, claims, evaluation, refs, model_dissent=False)
        context.egress_inspection = context.security.inspect_egress(text)
        if context.egress_inspection.status is InspectionStatus.BLOCKED:
            context.outcome = WorkflowOutcome.QUARANTINED
            context.failure_reason = context.egress_inspection.reason
            context.transition(CaseState.QUARANTINED, self.name, at, "egress safety inspection blocked the draft", refs)
            return
        context.memory_inspection = context.security.inspect_memory(text)
        if context.memory_inspection.status is InspectionStatus.BLOCKED:
            context.outcome = WorkflowOutcome.QUARANTINED
            context.failure_reason = context.memory_inspection.reason
            context.transition(CaseState.QUARANTINED, self.name, at, "memory safety inspection blocked the draft", refs)
            return
        context.transition(CaseState.DRAFT_READY, self.name, at, "draft built from policy and surfaced evidence", refs)
        context.transition(CaseState.AWAITING_CLINICIAN, self.name, at, "draft awaits the clinician veto holder")


class DeadlineSentinelAgent:
    name = "deadline_sentinel"

    def run(self, context: WorkflowContext, at: datetime) -> StatutoryClock:
        context.require_read(self.name, "case_state")
        context.require_read(self.name, "statutory_clock")
        context.require_write(self.name, "case_state")
        clock = context.machine.statutory_clock(context.case)
        try:
            if clock.is_expired(at) and CaseState.CLOSED_ABANDONED_DEADLINE in ALLOWED_TRANSITIONS[context.case.state]:
                context.transition(
                    CaseState.CLOSED_ABANDONED_DEADLINE,
                    self.name,
                    at,
                    "statutory clock expired before the required action",
                    actor_kind=ActorKind.SCHEDULER,
                )
                context.outcome = WorkflowOutcome.DEADLINE_ABANDONED
                context.failure_reason = "configured statutory clock expired"
                context.record(
                    self.name,
                    "expired",
                    "case closed after deadline expiry",
                    at,
                    actor_kind=ActorKind.SCHEDULER,
                    receipt_outcome="refused",
                    refusal_reason="statutory deadline expired",
                )
            else:
                context.record(
                    self.name,
                    "within_clock",
                    "deadline sentinel checked the case-bound statutory clock",
                    at,
                    actor_kind=ActorKind.SCHEDULER,
                )
        except UnverifiedDeadline:
            context.record(
                self.name,
                "unverified",
                "deadline sentinel refused to calculate an unverified clock",
                at,
                actor_kind=ActorKind.SCHEDULER,
            )
        return clock

class EscalationStrategistAgent:
    name = "escalation_strategist"

    def run(self, context: WorkflowContext, at: datetime) -> None:
        context.require_read(self.name, "case_memory")
        context.require_read(self.name, "surfaced_evidence")
        context.require_read(self.name, "policy_clause")
        context.require_write(self.name, "draft")
        context.require_write(self.name, "case_state")
        if context.case.state is not CaseState.DETERMINATION_RECEIVED:
            context.record(self.name, "waiting", "no escalation event requires re-derived argument", at)
            return
        context.transition(CaseState.ESCALATION_ELIGIBLE, self.name, at, "new review level requires a fresh evidentiary strategy")

    def rederive_argument(self, context: WorkflowContext, at: datetime) -> DraftPackage | None:
        """Build a new level-two argument from evidence, never old prose."""

        context.require_read(self.name, "case_memory")
        context.require_read(self.name, "surfaced_evidence")
        context.require_read(self.name, "policy_clause")
        context.require_write(self.name, "draft")
        if context.case.state is CaseState.DETERMINATION_RECEIVED:
            self.run(context, at)
        if context.case.state is not CaseState.ESCALATION_ELIGIBLE:
            return None
        match = context.policy_match
        evaluation = context.criterion_evaluation
        if match is None or evaluation is None or evaluation.status is not CriterionStatus.SATISFIED:
            context.record(self.name, "abstained", "escalation strategy lacks a satisfied criterion", at)
            return None
        observation_ids = tuple(
            observation.observation_id
            for observation in context.observations
            if observation.disposition is EvidenceDisposition.SATISFIED
        )
        claims = (
            DraftClaim(
                claim_id="claim.level-two-criterion-supported",
                criterion_id=match.criterion.criterion_id,
                text="At the escalated review level, the surfaced evidence still satisfies the cited criterion.",
                kind="supported",
                observation_ids=observation_ids,
            ),
        )
        validate_claims(match.criterion, evaluation, context.observations, claims)
        policy_ref = EvidenceRef(
            "PolicyClause",
            f"policy://{match.policy_id}/{match.criterion_id}",
            match.source_span.source_hash,
        )
        refs = (policy_ref,) + tuple(ref for observation in context.observations for ref in observation.references)
        draft = DraftPackage(
            "Level-two argument: re-derived from the criterion tree and current surfaced evidence.",
            claims,
            evaluation,
            refs,
            model_dissent=False,
        )
        context.record(self.name, "rederived", "escalation argument rebuilt from current evidence", at, refs)
        return draft
