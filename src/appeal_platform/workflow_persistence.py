"""Atomic Firestore persistence for a case and its resumable workflow session."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import importlib
from typing import Protocol, cast

from appeal_core import Case
from appeal_core.state_machine import JsonObject

from .sessions import WorkflowSession, WorkflowSessionConflict
from .store import CaseStoreConflict


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


class WorkflowPersistence(Protocol):
    """Persistence boundary that commits case and session state together."""

    def save_case_and_session(
        self,
        case: Case,
        session: WorkflowSession,
        *,
        expected_fingerprint: str | None = None,
    ) -> None: ...


def _require(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _firestore_id(value: str, label: str) -> str:
    value = _require(value, label)
    if "/" in value:
        raise ValueError(f"{label} must not contain '/'")
    return value


def _stored_case(document: Mapping[str, object], *, tenant_id: str, case_id: str) -> Case:
    if document.get("tenant_id") != tenant_id or document.get("case_id") != case_id:
        raise ValueError("stored case identity does not match its document path")
    payload = document.get("case")
    if not isinstance(payload, dict):
        raise ValueError("stored case payload must be an object")
    case = Case.from_json(cast(JsonObject, payload))
    if case.tenant_id != tenant_id or case.case_id != case_id:
        raise ValueError("stored case payload does not match its document path")
    if document.get("fingerprint") != case.fingerprint():
        raise CaseStoreConflict("stored case fingerprint does not match its payload")
    return case


def _stored_session(
    document: Mapping[str, object],
    *,
    tenant_id: str,
    case_id: str,
) -> WorkflowSession:
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


class FirestoreWorkflowPersistence:
    """Commit the immutable case and reference-only session in one transaction.

    Case state and its resumable workflow capsule must never be visible at
    different versions. A single Firestore transaction also makes concurrent
    Pub/Sub duplicate deliveries fail as a normal optimistic conflict instead
    of leaving a terminal case with a stale session.
    """

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
                raise RuntimeError("atomic workflow persistence requires google-cloud-firestore") from error
            factory = cast(_FirestoreFactory, getattr(firestore, "Client"))
            client = factory(project=project, database=database)
            transactional = cast(_TransactionalFactory, getattr(firestore, "transactional"))
        self._client = cast(_FirestoreClient, client)
        self._transactional = transactional
        self._root_collection = _firestore_id(root_collection, "Firestore root collection")

    def _case_ref(self, tenant_id: str, case_id: str) -> _DocumentReference:
        return (
            self._client.collection(self._root_collection)
            .document(_firestore_id(tenant_id, "tenant ID"))
            .collection("cases")
            .document(_firestore_id(case_id, "case ID"))
        )

    def _session_ref(self, tenant_id: str, case_id: str) -> _DocumentReference:
        return (
            self._case_ref(tenant_id, case_id)
            .collection("workflow_sessions")
            .document("current")
        )

    @staticmethod
    def _case_document(case: Case) -> dict[str, object]:
        return {
            "schema_version": 1,
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "state": case.state.value,
            "fingerprint": case.fingerprint(),
            "case": cast(dict[str, object], case.to_json()),
        }

    @staticmethod
    def _session_document(session: WorkflowSession) -> dict[str, object]:
        return {
            "schema_version": 1,
            "tenant_id": session.tenant_id,
            "case_id": session.case_id,
            "case_fingerprint": session.case_fingerprint,
            "session_fingerprint": session.fingerprint(),
            "session": session.to_json(),
        }

    @staticmethod
    def _read_case(
        snapshot: _DocumentSnapshot,
        *,
        tenant_id: str,
        case_id: str,
    ) -> Case | None:
        if not snapshot.exists:
            return None
        document = snapshot.to_dict()
        if document is None:
            raise ValueError("Firestore returned an empty case document")
        return _stored_case(document, tenant_id=tenant_id, case_id=case_id)

    @staticmethod
    def _read_session(
        snapshot: _DocumentSnapshot,
        *,
        tenant_id: str,
        case_id: str,
    ) -> WorkflowSession | None:
        if not snapshot.exists:
            return None
        document = snapshot.to_dict()
        if document is None:
            raise ValueError("Firestore returned an empty workflow session document")
        return _stored_session(document, tenant_id=tenant_id, case_id=case_id)

    def save_case_and_session(
        self,
        case: Case,
        session: WorkflowSession,
        *,
        expected_fingerprint: str | None = None,
    ) -> None:
        if session.tenant_id != case.tenant_id or session.case_id != case.case_id:
            raise WorkflowSessionConflict("workflow session identity does not match its case")
        current_fingerprint = case.fingerprint()
        if session.case_fingerprint != current_fingerprint:
            raise WorkflowSessionConflict("workflow session must bind to the case being persisted")

        case_ref = self._case_ref(case.tenant_id, case.case_id)
        session_ref = self._session_ref(case.tenant_id, case.case_id)

        def write(transaction: _Transaction) -> None:
            existing_case = self._read_case(
                case_ref.get(transaction=transaction),
                tenant_id=case.tenant_id,
                case_id=case.case_id,
            )
            existing_session = self._read_session(
                session_ref.get(transaction=transaction),
                tenant_id=case.tenant_id,
                case_id=case.case_id,
            )

            if existing_case is None:
                if expected_fingerprint is not None:
                    raise CaseStoreConflict("cannot compare an expected version for a new case")
            elif existing_case.fingerprint() != current_fingerprint and (
                expected_fingerprint is None or existing_case.fingerprint() != expected_fingerprint
            ):
                raise CaseStoreConflict("case version changed or expected_fingerprint was omitted")

            if existing_session is None:
                if expected_fingerprint is not None:
                    raise WorkflowSessionConflict("cannot compare an expected version for a new workflow session")
            elif not (
                existing_session.case_fingerprint == session.case_fingerprint
                and existing_session.fingerprint() == session.fingerprint()
            ) and (
                expected_fingerprint is None or existing_session.case_fingerprint != expected_fingerprint
            ):
                raise WorkflowSessionConflict("workflow session version changed or expected_fingerprint was omitted")

            if existing_case is None or existing_case.fingerprint() != current_fingerprint:
                transaction.set(case_ref, self._case_document(case))
            if existing_session is None or not (
                existing_session.case_fingerprint == session.case_fingerprint
                and existing_session.fingerprint() == session.fingerprint()
            ):
                transaction.set(session_ref, self._session_document(session))

        if self._transactional is not None:
            transaction = self._client.transaction()
            wrapped = self._transactional(write)
            cast(Callable[[_Transaction], object], wrapped)(transaction)
            return

        transaction = self._client.transaction()
        transaction.begin()
        write(transaction)
        transaction.commit()
