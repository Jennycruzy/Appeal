"""Reference-only workflow sessions for restart-safe local and cloud runs.

The session capsule is deliberately smaller than the workflow context. It
retains enough structured state to resume a human approval or payer
determination, while omitting denial bodies, chart resources, model output,
and draft prose.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import hashlib
import importlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast

from appeal_agents import AppealInput, AppealWorkflow, DenialDocument
from appeal_agents.agents import WorkflowContext
from appeal_agents.combinator import CombinatorDecision, VetoStatus, VetoVerdict
from appeal_agents.models import DraftPackage, PolicyMatch, WorkflowEvent, WorkflowOutcome
from appeal_agents.workflow import WorkflowResult
from appeal_agents.security import InspectionResult, InspectionStatus
from appeal_core import (
    Case,
    ClaimKind,
    CriterionEvaluation,
    CriterionStatus,
    DraftClaim,
    EvidenceDisposition,
    EvidenceObservation,
    EvidenceRef,
    PolicyCriterion,
)
from appeal_core.state_machine import JsonObject

from .payer import PayerDecision, PayerDecisionStatus


class WorkflowSessionConflict(ValueError):
    """Raised when a stale workflow session would overwrite a newer one."""


def _require(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: datetime, label: str) -> str:
    return _utc(value, label).isoformat().replace("+00:00", "Z")


def _datetime(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO-8601 datetime")
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")), label)
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO-8601 datetime") from error


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _string(value, label)


def _ref_json(ref: EvidenceRef) -> dict[str, object]:
    return {"kind": ref.kind, "uri": ref.uri, "sha256": ref.sha256}


def _ref(value: object, label: str) -> EvidenceRef:
    document = _object(value, label)
    return EvidenceRef(
        _string(document.get("kind"), f"{label}.kind"),
        _string(document.get("uri"), f"{label}.uri"),
        _string(document.get("sha256"), f"{label}.sha256"),
    )


def _refs_json(refs: tuple[EvidenceRef, ...]) -> list[dict[str, object]]:
    return [_ref_json(ref) for ref in refs]


def _refs(value: object, label: str) -> tuple[EvidenceRef, ...]:
    return tuple(_ref(item, f"{label}[{index}]") for index, item in enumerate(_array(value, label)))


def _observation_json(observation: EvidenceObservation) -> dict[str, object]:
    return {
        "observation_id": observation.observation_id,
        "leaf_criterion_id": observation.leaf_criterion_id,
        "disposition": observation.disposition.value,
        "evidence_type": observation.evidence_type,
        "references": _refs_json(observation.references),
    }


def _observation(value: object, label: str) -> EvidenceObservation:
    document = _object(value, label)
    disposition_text = _string(document.get("disposition"), f"{label}.disposition")
    try:
        disposition = EvidenceDisposition(disposition_text)
    except ValueError as error:
        raise ValueError(f"{label}.disposition is not supported") from error
    return EvidenceObservation(
        _string(document.get("observation_id"), f"{label}.observation_id"),
        _string(document.get("leaf_criterion_id"), f"{label}.leaf_criterion_id"),
        disposition,
        _string(document.get("evidence_type"), f"{label}.evidence_type"),
        _refs(document.get("references"), f"{label}.references"),
    )


def _evaluation_json(evaluation: CriterionEvaluation) -> dict[str, object]:
    return {
        "criterion_id": evaluation.criterion_id,
        "status": evaluation.status.value,
        "evidence_refs": _refs_json(evaluation.evidence_refs),
        "children": [_evaluation_json(child) for child in evaluation.children],
    }


def _evaluation(value: object, label: str) -> CriterionEvaluation:
    document = _object(value, label)
    status_text = _string(document.get("status"), f"{label}.status")
    try:
        status = CriterionStatus(status_text)
    except ValueError as error:
        raise ValueError(f"{label}.status is not supported") from error
    return CriterionEvaluation(
        _string(document.get("criterion_id"), f"{label}.criterion_id"),
        status,
        _refs(document.get("evidence_refs"), f"{label}.evidence_refs"),
        tuple(
            _evaluation(child, f"{label}.children[{index}]")
            for index, child in enumerate(_array(document.get("children"), f"{label}.children"))
        ),
    )


def _claim_json(claim: DraftClaim) -> dict[str, object]:
    # Claim prose is intentionally excluded. The claim identity and
    # observation binding are sufficient for the deterministic resume gate.
    return {
        "claim_id": claim.claim_id,
        "criterion_id": claim.criterion_id,
        "kind": claim.kind,
        "observation_ids": list(claim.observation_ids),
    }


def _claim(value: object, label: str) -> DraftClaim:
    document = _object(value, label)
    kind = _string(document.get("kind"), f"{label}.kind")
    if kind not in {"supported", "absence", "contradiction"}:
        raise ValueError(f"{label}.kind is not supported")
    observation_ids = tuple(
        _string(item, f"{label}.observation_ids[{index}]")
        for index, item in enumerate(_array(document.get("observation_ids"), f"{label}.observation_ids"))
    )
    return DraftClaim(
        _string(document.get("claim_id"), f"{label}.claim_id"),
        _string(document.get("criterion_id"), f"{label}.criterion_id"),
        "[claim prose omitted from durable workflow context]",
        cast(ClaimKind, kind),
        observation_ids,
    )


def _draft_json(draft: DraftPackage) -> dict[str, object]:
    return {
        "claims": [_claim_json(claim) for claim in draft.claims],
        "criterion_evaluation": _evaluation_json(draft.criterion_evaluation),
        "evidence_refs": _refs_json(draft.evidence_refs),
        "model_dissent": draft.model_dissent,
    }


def _draft(value: object, label: str) -> DraftPackage:
    document = _object(value, label)
    return DraftPackage(
        "[draft prose omitted from durable workflow context]",
        tuple(_claim(item, f"{label}.claims[{index}]") for index, item in enumerate(_array(document.get("claims"), f"{label}.claims"))),
        _evaluation(document.get("criterion_evaluation"), f"{label}.criterion_evaluation"),
        _refs(document.get("evidence_refs"), f"{label}.evidence_refs"),
        _boolean(document.get("model_dissent"), f"{label}.model_dissent"),
    )


def _inspection_json(inspection: InspectionResult | None) -> dict[str, object] | None:
    if inspection is None:
        return None
    return {
        "surface": inspection.surface,
        "status": inspection.status.value,
        "provider": inspection.provider,
        "categories": list(inspection.categories),
        "reason": inspection.reason,
    }


def _inspection(value: object, label: str) -> InspectionResult | None:
    if value is None:
        return None
    document = _object(value, label)
    status_text = _string(document.get("status"), f"{label}.status")
    try:
        status = InspectionStatus(status_text)
    except ValueError as error:
        raise ValueError(f"{label}.status is not supported") from error
    return InspectionResult(
        _string(document.get("surface"), f"{label}.surface"),
        status,
        _string(document.get("provider"), f"{label}.provider"),
        tuple(
            _string(item, f"{label}.categories[{index}]")
            for index, item in enumerate(_array(document.get("categories"), f"{label}.categories"))
        ),
        _string(document.get("reason"), f"{label}.reason"),
    )


def _verdict_json(verdict: VetoVerdict) -> dict[str, object]:
    return {"holder": verdict.holder, "status": verdict.status.value, "reason": verdict.reason}


def _verdict(value: object, label: str) -> VetoVerdict:
    document = _object(value, label)
    status_text = _string(document.get("status"), f"{label}.status")
    try:
        status = VetoStatus(status_text)
    except ValueError as error:
        raise ValueError(f"{label}.status is not supported") from error
    return VetoVerdict(
        _string(document.get("holder"), f"{label}.holder"),
        status,
        _string(document.get("reason"), f"{label}.reason"),
    )


def _combinator_json(combinator: CombinatorDecision | None) -> dict[str, object] | None:
    if combinator is None:
        return None
    return {
        "status": combinator.status.value,
        "verdicts": [_verdict_json(verdict) for verdict in combinator.verdicts],
        "model_dissent": combinator.model_dissent,
    }


def _combinator(value: object, label: str) -> CombinatorDecision | None:
    if value is None:
        return None
    document = _object(value, label)
    status_text = _string(document.get("status"), f"{label}.status")
    try:
        status = VetoStatus(status_text)
    except ValueError as error:
        raise ValueError(f"{label}.status is not supported") from error
    return CombinatorDecision(
        status,
        tuple(_verdict(item, f"{label}.verdicts[{index}]") for index, item in enumerate(_array(document.get("verdicts"), f"{label}.verdicts"))),
        _boolean(document.get("model_dissent"), f"{label}.model_dissent"),
    )


def _event_json(event: WorkflowEvent) -> dict[str, object]:
    return {
        "agent": event.agent,
        "status": event.status,
        "message": event.message,
        "recorded_at": _timestamp(event.recorded_at, "event.recorded_at"),
        "evidence_refs": _refs_json(event.evidence_refs),
    }


def _event(value: object, label: str) -> WorkflowEvent:
    document = _object(value, label)
    return WorkflowEvent(
        _string(document.get("agent"), f"{label}.agent"),
        _string(document.get("status"), f"{label}.status"),
        _string(document.get("message"), f"{label}.message"),
        _datetime(document.get("recorded_at"), f"{label}.recorded_at"),
        _refs(document.get("evidence_refs"), f"{label}.evidence_refs"),
    )


def _payer_json(decision: PayerDecision | None) -> dict[str, object] | None:
    if decision is None:
        return None
    return {
        "case_id": decision.case_id,
        "tenant_id": decision.tenant_id,
        "status": decision.status.value,
        "criterion_id": decision.criterion_id,
        "criterion_status": decision.criterion_status.value,
        "reason": decision.reason,
        "evidence_refs": _refs_json(decision.evidence_refs),
        "payer_graph_fingerprint": decision.payer_graph_fingerprint,
    }


def _payer(value: object, label: str) -> PayerDecision | None:
    if value is None:
        return None
    document = _object(value, label)
    status_text = _string(document.get("status"), f"{label}.status")
    criterion_status_text = _string(document.get("criterion_status"), f"{label}.criterion_status")
    try:
        status = PayerDecisionStatus(status_text)
        criterion_status = CriterionStatus(criterion_status_text)
    except ValueError as error:
        raise ValueError(f"{label} contains an unsupported status") from error
    return PayerDecision(
        _string(document.get("case_id"), f"{label}.case_id"),
        _string(document.get("tenant_id"), f"{label}.tenant_id"),
        status,
        _string(document.get("criterion_id"), f"{label}.criterion_id"),
        criterion_status,
        _string(document.get("reason"), f"{label}.reason"),
        _refs(document.get("evidence_refs"), f"{label}.evidence_refs"),
        _string(document.get("payer_graph_fingerprint"), f"{label}.payer_graph_fingerprint"),
    )


@dataclass(frozen=True)
class WorkflowSession:
    """The safe, structured subset required to resume a workflow."""

    tenant_id: str
    case_id: str
    case_fingerprint: str
    policy: PolicyCriterion | None
    observations: tuple[EvidenceObservation, ...]
    criterion_evaluation: CriterionEvaluation | None
    draft: DraftPackage | None
    combinator: CombinatorDecision | None
    inbound_inspection: InspectionResult | None
    egress_inspection: InspectionResult | None
    memory_inspection: InspectionResult | None
    events: tuple[WorkflowEvent, ...]
    outcome: WorkflowOutcome
    failure_reason: str | None
    mutation_count: int
    payer_decision: PayerDecision | None = None

    def __post_init__(self) -> None:
        _require(self.tenant_id, "session tenant ID")
        _require(self.case_id, "session case ID")
        _require(self.case_fingerprint, "session case fingerprint")
        if self.mutation_count < 0:
            raise ValueError("session mutation_count must not be negative")
        if self.policy is None and (self.observations or self.criterion_evaluation is not None or self.draft is not None):
            raise ValueError("session evidence requires a persisted policy criterion")

    @classmethod
    def from_result(cls, result: WorkflowResult, payer_decision: PayerDecision | None = None) -> "WorkflowSession":
        context = result.context
        return cls(
            tenant_id=result.case.tenant_id,
            case_id=result.case.case_id,
            case_fingerprint=result.case.fingerprint(),
            policy=context.input.policy if context is not None else None,
            observations=context.observations if context is not None else (),
            criterion_evaluation=context.criterion_evaluation if context is not None else None,
            draft=result.draft,
            combinator=result.combinator,
            inbound_inspection=context.inbound_inspection if context is not None else None,
            egress_inspection=context.egress_inspection if context is not None else None,
            memory_inspection=context.memory_inspection if context is not None else None,
            events=result.events,
            outcome=result.outcome,
            failure_reason=result.failure_reason,
            mutation_count=result.mutation_count,
            payer_decision=payer_decision,
        )

    def to_json(self) -> dict[str, object]:
        # No denial body, chart resource, model response, claim prose, or
        # draft prose is included in this document.
        return {
            "schema_version": 1,
            "tenant_id": self.tenant_id,
            "case_id": self.case_id,
            "case_fingerprint": self.case_fingerprint,
            "persistence_policy": "reference_only_no_denial_chart_model_or_draft_prose",
            "policy": self.policy.to_json() if self.policy is not None else None,
            "observations": [_observation_json(item) for item in self.observations],
            "criterion_evaluation": (
                _evaluation_json(self.criterion_evaluation) if self.criterion_evaluation is not None else None
            ),
            "draft": _draft_json(self.draft) if self.draft is not None else None,
            "combinator": _combinator_json(self.combinator),
            "inspections": {
                "inbound": _inspection_json(self.inbound_inspection),
                "egress": _inspection_json(self.egress_inspection),
                "memory": _inspection_json(self.memory_inspection),
            },
            "events": [_event_json(event) for event in self.events],
            "outcome": self.outcome.value,
            "failure_reason": self.failure_reason,
            "mutation_count": self.mutation_count,
            "payer_decision": _payer_json(self.payer_decision),
        }

    def fingerprint(self) -> str:
        canonical = json.dumps(self.to_json(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def from_json(cls, document: Mapping[str, object]) -> "WorkflowSession":
        if document.get("schema_version") != 1:
            raise ValueError("unsupported workflow session schema")
        policy_value = document.get("policy")
        if policy_value is not None and not isinstance(policy_value, dict):
            raise ValueError("session.policy must be an object or null")
        policy = PolicyCriterion.from_json(cast(JsonObject, policy_value)) if policy_value is not None else None
        outcome_text = _string(document.get("outcome"), "session.outcome")
        try:
            outcome = WorkflowOutcome(outcome_text)
        except ValueError as error:
            raise ValueError("session.outcome is not supported") from error
        inspections = _object(document.get("inspections"), "session.inspections")
        failure_reason = _optional_string(document.get("failure_reason"), "session.failure_reason")
        mutation_count = document.get("mutation_count")
        if not isinstance(mutation_count, int) or isinstance(mutation_count, bool):
            raise ValueError("session.mutation_count must be an integer")
        return cls(
            tenant_id=_string(document.get("tenant_id"), "session.tenant_id"),
            case_id=_string(document.get("case_id"), "session.case_id"),
            case_fingerprint=_string(document.get("case_fingerprint"), "session.case_fingerprint"),
            policy=policy,
            observations=tuple(
                _observation(item, f"session.observations[{index}]")
                for index, item in enumerate(_array(document.get("observations"), "session.observations"))
            ),
            criterion_evaluation=(
                _evaluation(document.get("criterion_evaluation"), "session.criterion_evaluation")
                if document.get("criterion_evaluation") is not None
                else None
            ),
            draft=_draft(document.get("draft"), "session.draft") if document.get("draft") is not None else None,
            combinator=_combinator(document.get("combinator"), "session.combinator"),
            inbound_inspection=_inspection(inspections.get("inbound"), "session.inspections.inbound"),
            egress_inspection=_inspection(inspections.get("egress"), "session.inspections.egress"),
            memory_inspection=_inspection(inspections.get("memory"), "session.inspections.memory"),
            events=tuple(
                _event(item, f"session.events[{index}]")
                for index, item in enumerate(_array(document.get("events"), "session.events"))
            ),
            outcome=outcome,
            failure_reason=failure_reason,
            mutation_count=mutation_count,
            payer_decision=_payer(document.get("payer_decision"), "session.payer_decision"),
        )

    def to_runtime_result(self, workflow: AppealWorkflow, case: Case) -> "RuntimeResumeLike":
        if case.tenant_id != self.tenant_id or case.case_id != self.case_id:
            raise ValueError("workflow session identity does not match its case")
        if case.fingerprint() != self.case_fingerprint:
            raise WorkflowSessionConflict("workflow session is stale for the persisted case")
        policy = self.policy
        placeholder_denial = DenialDocument.from_content(
            f"resume://{case.tenant_id}/{case.case_id}",
            "application/x-appeal-resume-capsule",
            "original denial omitted from durable workflow context",
        )
        appeal_input = AppealInput(
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            patient_id="patient-omitted-from-durable-context",
            received_at=case.transitions[0].entered_at,
            denial=placeholder_denial,
            policy=policy,
            chart=(),
        )
        context = WorkflowContext(
            appeal_input,
            workflow.machine,
            case,
            workflow.security,
            workflow.ledger,
            workflow.policies,
            inbound_inspection=self.inbound_inspection,
            egress_inspection=self.egress_inspection,
            memory_inspection=self.memory_inspection,
            observations=self.observations,
            criterion_evaluation=self.criterion_evaluation,
            draft=self.draft,
            combinator_decision=self.combinator,
            events=list(self.events),
            outcome=self.outcome,
            failure_reason=self.failure_reason,
        )
        if policy is not None:
            context.policy_match = PolicyMatch(policy.policy_id, policy.criterion_id, policy, policy.source_span)
        return RuntimeResumeLike(
            workflow=WorkflowResult(
                outcome=self.outcome,
                case_state=case.state,
                case=case,
                clock=workflow.machine.statutory_clock(case),
                events=self.events,
                draft=self.draft,
                combinator=self.combinator,
                failure_reason=self.failure_reason,
                mutation_count=self.mutation_count,
                context=context,
            ),
            payer_decision=self.payer_decision,
        )


@dataclass(frozen=True)
class RuntimeResumeLike:
    workflow: WorkflowResult
    payer_decision: PayerDecision | None


class WorkflowSessionStore(Protocol):
    def save(self, session: WorkflowSession, *, expected_fingerprint: str | None = None) -> WorkflowSession: ...

    def get(self, tenant_id: str, case_id: str) -> WorkflowSession | None: ...


class LocalWorkflowSessionStore:
    """In-process session store used by local development and tests."""

    def __init__(self) -> None:
        self._sessions: dict[tuple[str, str], WorkflowSession] = {}

    def save(self, session: WorkflowSession, *, expected_fingerprint: str | None = None) -> WorkflowSession:
        key = (session.tenant_id, session.case_id)
        existing = self._sessions.get(key)
        if existing is None:
            if expected_fingerprint is not None:
                raise WorkflowSessionConflict("cannot compare an expected version for a new workflow session")
        elif existing.case_fingerprint == session.case_fingerprint and existing.fingerprint() == session.fingerprint():
            return existing
        elif expected_fingerprint is None or existing.case_fingerprint != expected_fingerprint:
            raise WorkflowSessionConflict("workflow session version changed or expected_fingerprint was omitted")
        self._sessions[key] = session
        return session

    def get(self, tenant_id: str, case_id: str) -> WorkflowSession | None:
        _require(tenant_id, "tenant ID")
        _require(case_id, "case ID")
        return self._sessions.get((tenant_id, case_id))


class _DocumentSnapshot(Protocol):
    @property
    def exists(self) -> bool: ...

    def to_dict(self) -> Mapping[str, object] | None: ...


class _DocumentReference(Protocol):
    def get(self, *, transaction: object | None = None) -> _DocumentSnapshot: ...

    def set(self, document_data: Mapping[str, object], *, transaction: object | None = None) -> object: ...

    def collection(self, collection_id: str) -> "_CollectionReference": ...


class _CollectionReference(Protocol):
    def document(self, document_id: str) -> _DocumentReference: ...

    def collection(self, collection_id: str) -> "_CollectionReference": ...


class _Transaction(Protocol):
    def set(self, document_ref: _DocumentReference, document_data: Mapping[str, object]) -> object: ...

    def begin(self) -> object: ...

    def commit(self) -> object: ...


class _FirestoreClient(Protocol):
    def collection(self, collection_path: str) -> _CollectionReference: ...

    def transaction(self) -> _Transaction: ...


class _FirestoreFactory(Protocol):
    def __call__(self, *, project: str | None, database: str) -> object: ...


class _TransactionalFactory(Protocol):
    def __call__(self, function: Callable[..., object]) -> Callable[..., object]: ...


def _firestore_id(value: str, label: str) -> str:
    value = _require(value, label)
    if "/" in value:
        raise ValueError(f"{label} must not contain '/'")
    return value


class FirestoreWorkflowSessionStore:
    """Firestore-backed reference-only workflow session store."""

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str = "(default)",
        root_collection: str = "appeal_tenants",
        client: object | None = None,
    ) -> None:
        transactional: _TransactionalFactory | None = None
        if client is None:
            try:
                firestore = importlib.import_module("google.cloud.firestore")
            except ImportError as error:
                raise RuntimeError(
                    "Firestore workflow sessions require the google-cloud-firestore package"
                ) from error
            factory = cast(_FirestoreFactory, getattr(firestore, "Client"))
            client = factory(project=project, database=database)
            transactional = cast(_TransactionalFactory, getattr(firestore, "transactional"))
        self._client = cast(_FirestoreClient, client)
        self._transactional = transactional
        self._root_collection = _firestore_id(root_collection, "Firestore root collection")

    def _session_ref(self, tenant_id: str, case_id: str) -> _DocumentReference:
        return (
            self._client.collection(self._root_collection)
            .document(_firestore_id(tenant_id, "tenant ID"))
            .collection("cases")
            .document(_firestore_id(case_id, "case ID"))
            .collection("workflow_sessions")
            .document("current")
        )

    @staticmethod
    def _document(session: WorkflowSession) -> dict[str, object]:
        return {
            "schema_version": 1,
            "tenant_id": session.tenant_id,
            "case_id": session.case_id,
            "case_fingerprint": session.case_fingerprint,
            "session_fingerprint": session.fingerprint(),
            "session": session.to_json(),
        }

    @staticmethod
    def _read(snapshot: _DocumentSnapshot, *, tenant_id: str, case_id: str) -> WorkflowSession | None:
        if not snapshot.exists:
            return None
        document = snapshot.to_dict()
        if document is None:
            raise ValueError("Firestore returned an empty workflow session document")
        if document.get("tenant_id") != tenant_id or document.get("case_id") != case_id:
            raise ValueError("workflow session identity does not match its document path")
        payload = document.get("session")
        if not isinstance(payload, dict):
            raise ValueError("stored workflow session payload must be an object")
        session = WorkflowSession.from_json(payload)
        if session.tenant_id != tenant_id or session.case_id != case_id:
            raise ValueError("workflow session payload does not match its document path")
        if document.get("case_fingerprint") != session.case_fingerprint:
            raise WorkflowSessionConflict("stored workflow session case fingerprint does not match its payload")
        if document.get("session_fingerprint") != session.fingerprint():
            raise WorkflowSessionConflict("stored workflow session fingerprint does not match its payload")
        return session

    def save(self, session: WorkflowSession, *, expected_fingerprint: str | None = None) -> WorkflowSession:
        ref = self._session_ref(session.tenant_id, session.case_id)

        def write(transaction: _Transaction) -> tuple[WorkflowSession, bool]:
            existing = self._read(
                ref.get(transaction=transaction),
                tenant_id=session.tenant_id,
                case_id=session.case_id,
            )
            if existing is None:
                if expected_fingerprint is not None:
                    raise WorkflowSessionConflict("cannot compare an expected version for a new workflow session")
            elif existing.case_fingerprint == session.case_fingerprint and existing.fingerprint() == session.fingerprint():
                return existing, False
            elif expected_fingerprint is None or existing.case_fingerprint != expected_fingerprint:
                raise WorkflowSessionConflict("workflow session version changed or expected_fingerprint was omitted")
            transaction.set(ref, self._document(session))
            return session, True

        if self._transactional is not None:
            transaction = self._client.transaction()
            wrapped = self._transactional(write)
            saved, _ = cast(Callable[[_Transaction], tuple[WorkflowSession, bool]], wrapped)(transaction)
            return saved

        transaction = self._client.transaction()
        transaction.begin()
        saved, changed = write(transaction)
        if changed:
            transaction.commit()
        return saved

    def get(self, tenant_id: str, case_id: str) -> WorkflowSession | None:
        tenant_id = _require(tenant_id, "tenant ID")
        case_id = _require(case_id, "case ID")
        return self._read(
            self._session_ref(tenant_id, case_id).get(),
            tenant_id=tenant_id,
            case_id=case_id,
        )
