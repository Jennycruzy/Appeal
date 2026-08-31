"""A bounded, stateless payer determination service."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from appeal_agents.demo import demo_policy
from appeal_core import EvidenceDisposition, EvidenceObservation, EvidenceRef
from appeal_platform import PayerAdjudicator, PayerDecision


class PayerServiceRequestError(ValueError):
    """Raised when a payer request is malformed or outside its scope."""


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PayerServiceRequestError(f"{label} must be a non-empty string")
    if len(value) > 512:
        raise PayerServiceRequestError(f"{label} is too long")
    return value


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise PayerServiceRequestError(f"{label} must be an object")
    return {str(key): cast(object, item) for key, item in value.items()}


def _references(value: object, label: str) -> tuple[EvidenceRef, ...]:
    if not isinstance(value, list):
        raise PayerServiceRequestError(f"{label} must be an array")
    if len(value) > 32:
        raise PayerServiceRequestError(f"{label} exceeds the reference limit")
    references: list[EvidenceRef] = []
    for index, item in enumerate(value):
        document = _object(item, f"{label}[{index}]")
        if set(document) != {"kind", "uri", "sha256"}:
            raise PayerServiceRequestError(f"{label}[{index}] must contain reference fields only")
        references.append(
            EvidenceRef(
                _string(document.get("kind"), f"{label}[{index}].kind"),
                _string(document.get("uri"), f"{label}[{index}].uri"),
                _string(document.get("sha256"), f"{label}[{index}].sha256"),
            )
        )
    return tuple(references)


def _observations(value: object) -> tuple[EvidenceObservation, ...]:
    if not isinstance(value, list):
        raise PayerServiceRequestError("observations must be an array")
    if len(value) > 32:
        raise PayerServiceRequestError("observations exceeds the reference limit")
    observations: list[EvidenceObservation] = []
    for index, item in enumerate(value):
        document = _object(item, f"observations[{index}]")
        try:
            disposition = EvidenceDisposition(_string(document.get("disposition"), f"observations[{index}].disposition"))
        except ValueError as error:
            raise PayerServiceRequestError(f"observations[{index}].disposition is unsupported") from error
        observations.append(
            EvidenceObservation(
                _string(document.get("observation_id"), f"observations[{index}].observation_id"),
                _string(document.get("leaf_criterion_id"), f"observations[{index}].leaf_criterion_id"),
                disposition,
                _string(document.get("evidence_type"), f"observations[{index}].evidence_type"),
                _references(document.get("references"), f"observations[{index}].references"),
            )
        )
    return tuple(observations)


@dataclass(frozen=True)
class PayerServiceRequest:
    tenant_id: str
    case_id: str
    idempotency_key: str
    observations: tuple[EvidenceObservation, ...]


class PayerService:
    """Determine a payer outcome without access to Appeal case state."""

    identity = "appeal-payer-service-v0.1"
    synthetic_only = True

    def __init__(self) -> None:
        # This private copy is deliberately created inside the payer service;
        # callers cannot submit a policy tree or mutate the Appeal copy.
        self._adjudicator = PayerAdjudicator(demo_policy())

    @property
    def criterion_fingerprint(self) -> str:
        return self._adjudicator.criterion.fingerprint()

    def parse_request(self, payload: Mapping[str, object]) -> PayerServiceRequest:
        allowed_fields = {"tenant_id", "case_id", "idempotency_key", "observations"}
        if set(payload) != allowed_fields:
            raise PayerServiceRequestError("payer request contains unsupported fields")
        tenant_id = _string(payload.get("tenant_id"), "tenant_id")
        case_id = _string(payload.get("case_id"), "case_id")
        if not tenant_id.startswith("tenant-demo"):
            raise PayerServiceRequestError("synthetic payer service requires a demo tenant")
        if not case_id.startswith("case-"):
            raise PayerServiceRequestError("synthetic payer service requires a synthetic case")
        idempotency_key = _string(payload.get("idempotency_key"), "idempotency_key")
        if not idempotency_key.startswith(f"{case_id}:payer:"):
            raise PayerServiceRequestError("idempotency_key must be scoped to the case payer action")
        return PayerServiceRequest(tenant_id, case_id, idempotency_key, _observations(payload.get("observations")))

    def determine(self, payload: Mapping[str, object]) -> dict[str, object]:
        request = self.parse_request(payload)
        decision = self._adjudicator.adjudicate(
            request.case_id,
            request.tenant_id,
            request.observations,
        )
        return self._public_result(request, decision)

    def _public_result(self, request: PayerServiceRequest, decision: PayerDecision) -> dict[str, object]:
        return {
            "schema_version": "0.1",
            "service": self.identity,
            "synthetic_only": self.synthetic_only,
            "tenant_id": request.tenant_id,
            "case_id": request.case_id,
            "idempotency_key": request.idempotency_key,
            "status": decision.status.value,
            "criterion_id": decision.criterion_id,
            "criterion_status": decision.criterion_status.value,
            "evidence_ref_count": len(decision.evidence_refs),
            "payer_graph_fingerprint": decision.payer_graph_fingerprint,
            "external_mutation_count": 0,
            "mutation_authority": False,
        }
