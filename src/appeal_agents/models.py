"""Data contracts passed between the local Appeal agent roles.

The models deliberately separate untrusted intake content, surfaced chart
observations, policy criteria, and drafted claims. Receipt code receives only
hashes and references; it never receives the document or chart body.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Final

from appeal_core import (
    Case,
    CriterionEvaluation,
    DraftClaim,
    EvidenceObservation,
    EvidenceRef,
    PolicyCriterion,
    SourceSpan,
)


class WorkflowOutcome(str, Enum):
    AWAITING_CLINICIAN = "awaiting_clinician"
    SUBMITTED = "submitted"
    ABSTAINED = "abstained"
    QUARANTINED = "quarantined"
    VETOED = "vetoed"
    ESCALATION_READY = "escalation_ready"
    CLOSED_WON = "closed_won"
    DEADLINE_ABANDONED = "deadline_abandoned"
    FAILED = "failed"


def _require_nonempty(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _require_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DenialDocument:
    """An untrusted denial document, retained only in the in-process context."""

    uri: str
    media_type: str
    content: str
    source_hash: str

    def __post_init__(self) -> None:
        _require_nonempty(self.uri, "denial URI")
        _require_nonempty(self.media_type, "denial media type")
        _require_nonempty(self.content, "denial content")
        if self.source_hash != _sha256(self.content):
            raise ValueError("denial source_hash must match the document content")

    @classmethod
    def from_content(cls, uri: str, media_type: str, content: str) -> "DenialDocument":
        return cls(uri, media_type, content, _sha256(content))

    @property
    def multimodal_required(self) -> bool:
        return self.media_type == "application/pdf" or self.media_type.startswith("image/")


@dataclass(frozen=True)
class FhirResource:
    """A small FHIR-shaped chart resource used by the local Evidence Miner."""

    resource_type: str
    resource_id: str
    patient_id: str
    code: str
    display: str
    status: str = "final"

    def __post_init__(self) -> None:
        for value, label in [
            (self.resource_type, "FHIR resource_type"),
            (self.resource_id, "FHIR resource_id"),
            (self.patient_id, "FHIR patient_id"),
            (self.code, "FHIR code"),
            (self.display, "FHIR display"),
            (self.status, "FHIR status"),
        ]:
            _require_nonempty(value, label)

    def evidence_ref(self, case_id: str) -> EvidenceRef:
        payload = json.dumps(
            {
                "resource_type": self.resource_type,
                "resource_id": self.resource_id,
                "patient_id": self.patient_id,
                "code": self.code,
                "display": self.display,
                "status": self.status,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return EvidenceRef(
            kind=f"FHIR.{self.resource_type}",
            uri=f"fhir://case/{case_id}/{self.resource_type}/{self.resource_id}",
            sha256=_sha256(payload),
        )


@dataclass(frozen=True)
class AppealInput:
    case_id: str
    tenant_id: str
    patient_id: str
    received_at: datetime
    denial: DenialDocument
    policy: PolicyCriterion | None
    chart: tuple[FhirResource, ...]

    def __post_init__(self) -> None:
        for value, label in [
            (self.case_id, "case ID"),
            (self.tenant_id, "tenant ID"),
            (self.patient_id, "patient ID"),
        ]:
            _require_nonempty(value, label)
        _require_utc(self.received_at, "received_at")
        for resource in self.chart:
            if resource.patient_id != self.patient_id:
                raise ValueError("AppealInput chart may contain only the scoped patient")


@dataclass(frozen=True)
class DenialParse:
    requested_item: str
    reason_code: str
    diagnosis: str
    policy_reference: str
    spans: tuple[SourceSpan, ...]

    def __post_init__(self) -> None:
        for value, label in [
            (self.requested_item, "requested item"),
            (self.reason_code, "reason code"),
            (self.diagnosis, "diagnosis"),
            (self.policy_reference, "policy reference"),
        ]:
            _require_nonempty(value, label)


@dataclass(frozen=True)
class PolicyMatch:
    policy_id: str
    criterion_id: str
    criterion: PolicyCriterion
    source_span: SourceSpan


@dataclass(frozen=True)
class DraftPackage:
    """A draft plus only the surfaced claims used to construct it."""

    text: str
    claims: tuple[DraftClaim, ...]
    criterion_evaluation: CriterionEvaluation
    evidence_refs: tuple[EvidenceRef, ...]
    model_dissent: bool

    def __post_init__(self) -> None:
        _require_nonempty(self.text, "draft text")


@dataclass(frozen=True)
class WorkflowEvent:
    agent: str
    status: str
    message: str
    recorded_at: datetime
    evidence_refs: tuple[EvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty(self.agent, "event agent")
        _require_nonempty(self.status, "event status")
        _require_nonempty(self.message, "event message")
        _require_utc(self.recorded_at, "event recorded_at")


AGENT_IDENTITIES: Final[dict[str, str]] = {
    "intake": "appeal-intake-local-v0.1",
    "denial_parser": "appeal-denial-parser-local-v0.1",
    "policy_analyst": "appeal-policy-analyst-local-v0.1",
    "evidence_miner": "appeal-evidence-miner-local-v0.1",
    "argument_builder": "appeal-argument-builder-local-v0.1",
    "deadline_sentinel": "appeal-deadline-sentinel-local-v0.1",
    "escalation_strategist": "appeal-escalation-strategist-local-v0.1",
    "veto_combinator": "appeal-veto-combinator-local-v0.1",
    "submission_gate": "appeal-submission-gate-local-v0.1",
}
