"""A separate local payer adjudicator with its own immutable criterion graph."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from appeal_core import (
    CriterionStatus,
    EvidenceObservation,
    EvidenceRef,
    PolicyCriterion,
    SourceSpan,
    evaluate_criterion,
)


class PayerDecisionStatus(str, Enum):
    FAVORABLE = "favorable"
    UNFAVORABLE = "unfavorable"
    PENDED = "pended"


def _require(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _clone_criterion(node: PolicyCriterion) -> PolicyCriterion:
    return PolicyCriterion(
        policy_id=node.policy_id,
        payer=node.payer,
        section_ref=node.section_ref,
        cpt_codes=node.cpt_codes,
        effective_date=node.effective_date,
        criterion_id=node.criterion_id,
        text=node.text,
        logic=node.logic,
        children=tuple(_clone_criterion(child) for child in node.children),
        satisfied_by=node.satisfied_by,
        source_hash=node.source_hash,
        source_span=SourceSpan(
            source_hash=node.source_span.source_hash,
            start_offset=node.source_span.start_offset,
            end_offset=node.source_span.end_offset,
            quote=node.source_span.quote,
        ),
    )


@dataclass(frozen=True)
class PayerDecision:
    case_id: str
    tenant_id: str
    status: PayerDecisionStatus
    criterion_id: str
    criterion_status: CriterionStatus
    reason: str
    evidence_refs: tuple[EvidenceRef, ...]
    payer_graph_fingerprint: str

    def to_json(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "tenant_id": self.tenant_id,
            "status": self.status.value,
            "criterion_id": self.criterion_id,
            "criterion_status": self.criterion_status.value,
            "reason": self.reason,
            "evidence_ref_count": len(self.evidence_refs),
            "payer_graph_fingerprint": self.payer_graph_fingerprint,
        }


class PayerAdjudicator:
    """Adjudicate against a private copy of a payer criterion.

    The service receives surfaced EvidenceObservation objects only. It has no
    chart reader and no reference to CaseStore, which makes the local
    separation explicit before the service accounts are deployed.
    """

    identity = "appeal-payer-adjudicator-local-v0.1"

    def __init__(self, criterion: PolicyCriterion) -> None:
        self._criterion = _clone_criterion(criterion)

    @property
    def criterion(self) -> PolicyCriterion:
        return self._criterion

    def adjudicate(
        self,
        case_id: str,
        tenant_id: str,
        observations: tuple[EvidenceObservation, ...],
    ) -> PayerDecision:
        case_id = _require(case_id, "payer case ID")
        tenant_id = _require(tenant_id, "payer tenant ID")
        evaluation = evaluate_criterion(self._criterion, observations)
        if evaluation.status is CriterionStatus.SATISFIED:
            status = PayerDecisionStatus.FAVORABLE
            reason = "payer criterion graph is satisfied by the surfaced evidence"
        elif evaluation.status is CriterionStatus.ABSENT:
            status = PayerDecisionStatus.PENDED
            reason = "payer criterion graph lacks required evidence"
        elif evaluation.status is CriterionStatus.CONTRADICTED:
            status = PayerDecisionStatus.UNFAVORABLE
            reason = "payer criterion graph is contradicted by the surfaced evidence"
        else:
            status = PayerDecisionStatus.PENDED
            reason = "payer criterion graph received conflicting evidence"
        return PayerDecision(
            case_id,
            tenant_id,
            status,
            self._criterion.criterion_id,
            evaluation.status,
            reason,
            evaluation.evidence_refs,
            self._criterion.fingerprint(),
        )
