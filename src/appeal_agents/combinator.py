"""The four-veto combinator.

Models can supply extraction and draft proposals, but only deterministic
checks and a clinician can clear the submission gate. The strictest verdict
always wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, Enum

from appeal_core import CriterionStatus

from .security import InspectionResult, InspectionStatus


class VetoStatus(str, Enum):
    CLEARED = "cleared"
    NEEDS_HUMAN = "needs_human"
    BLOCKED = "blocked"


class _Strictness(IntEnum):
    CLEARED = 0
    NEEDS_HUMAN = 1
    BLOCKED = 2


@dataclass(frozen=True)
class VetoVerdict:
    holder: str
    status: VetoStatus
    reason: str


@dataclass(frozen=True)
class CombinatorDecision:
    status: VetoStatus
    verdicts: tuple[VetoVerdict, ...]
    model_dissent: bool

    @property
    def can_submit(self) -> bool:
        return self.status is VetoStatus.CLEARED


def _strictest(verdicts: tuple[VetoVerdict, ...]) -> VetoStatus:
    return max(verdicts, key=lambda item: _Strictness[item.status.name]).status


class VetoCombinator:
    """Evaluate criterion, Evidence Floor, safety, and clinician vetoes."""

    def evaluate(
        self,
        *,
        criterion_status: CriterionStatus,
        evidence_floor_passed: bool,
        inbound_inspection: InspectionResult,
        egress_inspection: InspectionResult,
        memory_inspection: InspectionResult,
        clinician_decision: bool | None,
        model_dissent: bool,
    ) -> CombinatorDecision:
        criterion_verdict = VetoVerdict(
            holder="criterion_tree",
            status=(
                VetoStatus.CLEARED
                if criterion_status is CriterionStatus.SATISFIED
                else VetoStatus.BLOCKED
            ),
            reason=(
                "deterministic criterion tree is satisfied"
                if criterion_status is CriterionStatus.SATISFIED
                else f"criterion tree status is {criterion_status.value}"
            ),
        )
        evidence_verdict = VetoVerdict(
            holder="evidence_floor",
            status=VetoStatus.CLEARED if evidence_floor_passed else VetoStatus.BLOCKED,
            reason=(
                "every draft claim is traceable to surfaced evidence"
                if evidence_floor_passed
                else "one or more draft claims exceed surfaced evidence"
            ),
        )
        safety_blocked = (
            inbound_inspection.status is InspectionStatus.BLOCKED
            or egress_inspection.status is InspectionStatus.BLOCKED
            or memory_inspection.status is InspectionStatus.BLOCKED
        )
        safety_verdict = VetoVerdict(
            holder="model_armor_plus_gemma_tripwire",
            status=VetoStatus.BLOCKED if safety_blocked else VetoStatus.CLEARED,
            reason=(
                "inbound, egress, or memory safety inspection blocked the path"
                if safety_blocked
                else "inbound, egress, and memory safety inspections are clear"
            ),
        )
        if clinician_decision is True:
            clinician_verdict = VetoVerdict("clinician", VetoStatus.CLEARED, "clinician approved the draft")
        elif clinician_decision is False:
            clinician_verdict = VetoVerdict("clinician", VetoStatus.BLOCKED, "clinician vetoed the draft")
        else:
            clinician_verdict = VetoVerdict("clinician", VetoStatus.NEEDS_HUMAN, "clinician co-signature is pending")
        verdicts = (criterion_verdict, evidence_verdict, safety_verdict, clinician_verdict)
        return CombinatorDecision(_strictest(verdicts), verdicts, model_dissent)
