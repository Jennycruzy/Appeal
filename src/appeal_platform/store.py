"""Tenant-scoped case storage with local and Firestore implementations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol, cast

from appeal_core import Case
from appeal_core.state_machine import JsonObject


class CaseStoreScopeError(ValueError):
    """Raised when a case is accessed outside its tenant scope."""


class CaseStoreConflict(ValueError):
    """Raised when a write would silently overwrite another case version."""


def _require(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


class CaseStore:
    """An in-process tenant-partitioned store for local development."""

    def __init__(self) -> None:
        self._cases: dict[tuple[str, str], Case] = {}

    def save(self, case: Case, *, expected_fingerprint: str | None = None) -> Case:
        key = (case.tenant_id, case.case_id)
        existing = self._cases.get(key)
        if existing is None:
            if expected_fingerprint is not None:
                raise CaseStoreConflict("cannot compare an expected version for a new case")
            self._cases[key] = case
            return case
        if existing.fingerprint() == case.fingerprint():
            return existing
        if expected_fingerprint is None or existing.fingerprint() != expected_fingerprint:
            raise CaseStoreConflict("case version changed or expected_fingerprint was omitted")
        self._cases[key] = case
        return case

    def get(self, tenant_id: str, case_id: str) -> Case | None:
        tenant_id = _require(tenant_id, "tenant ID")
        case_id = _require(case_id, "case ID")
        case = self._cases.get((tenant_id, case_id))
        if case is not None and case.tenant_id != tenant_id:
            raise CaseStoreScopeError("case belongs to another tenant")
        return case

    def require(self, tenant_id: str, case_id: str) -> Case:
        case = self.get(tenant_id, case_id)
        if case is None:
            raise KeyError(f"case {case_id!r} was not found in tenant {tenant_id!r}")
        return case

    def list_tenant(self, tenant_id: str) -> tuple[Case, ...]:
        tenant_id = _require(tenant_id, "tenant ID")
        return tuple(case for (scope, _), case in self._cases.items() if scope == tenant_id)

    def count(self) -> int:
        return len(self._cases)


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

    def stream(self) -> Iterable[_DocumentSnapshot]: ...


class _Transaction(Protocol):
    def commit(self) -> object: ...


class _FirestoreClient(Protocol):
    def collection(self, collection_path: str) -> _CollectionReference: ...

    def collection_group(self, collection_id: str) -> _CollectionReference: ...

    def transaction(self) -> _Transaction: ...


def _firestore_id(value: str, label: str) -> str:
    value = _require(value, label)
    if "/" in value:
        raise ValueError(f"{label} must not contain '/'")
    return value


def _stored_case(document: Mapping[str, object], *, tenant_id: str, case_id: str) -> Case:
    stored_tenant = document.get("tenant_id")
    stored_case = document.get("case_id")
    if stored_tenant != tenant_id or stored_case != case_id:
        raise CaseStoreScopeError("stored case identity does not match its document path")
    payload = document.get("case")
    if not isinstance(payload, dict):
        raise ValueError("stored case payload must be an object")
    case = Case.from_json(cast(JsonObject, payload))
    if case.tenant_id != tenant_id or case.case_id != case_id:
        raise CaseStoreScopeError("stored case payload does not match its document path")
    fingerprint = document.get("fingerprint")
    if fingerprint != case.fingerprint():
        raise CaseStoreConflict("stored case fingerprint does not match its payload")
    return case


class FirestoreCaseStore(CaseStore):
    """A tenant-scoped Firestore store for case state and safe references.

    The document contains the immutable case state machine, evidence references,
    and receipt-facing metadata. It never receives denial prose, chart content,
    model responses, or other unbounded document payloads.
    """

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str = "(default)",
        root_collection: str = "appeal_tenants",
        client: object | None = None,
    ) -> None:
        if client is None:
            try:
                from google.cloud import firestore  # type: ignore[import-untyped]
            except ImportError as error:
                raise RuntimeError(
                    "Firestore storage requires the google-cloud-firestore package"
                ) from error
            client = firestore.Client(project=project, database=database)
        self._client = cast(_FirestoreClient, client)
        self._root_collection = _firestore_id(root_collection, "Firestore root collection")

    def _case_ref(self, tenant_id: str, case_id: str) -> _DocumentReference:
        tenant_id = _firestore_id(tenant_id, "tenant ID")
        case_id = _firestore_id(case_id, "case ID")
        return (
            self._client.collection(self._root_collection)
            .document(tenant_id)
            .collection("cases")
            .document(case_id)
        )

    @staticmethod
    def _document(case: Case) -> dict[str, object]:
        return {
            "schema_version": 1,
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "state": case.state.value,
            "fingerprint": case.fingerprint(),
            "case": cast(dict[str, object], case.to_json()),
        }

    @staticmethod
    def _read(snapshot: _DocumentSnapshot, *, tenant_id: str, case_id: str) -> Case | None:
        if not snapshot.exists:
            return None
        document = snapshot.to_dict()
        if document is None:
            raise ValueError("Firestore returned an empty case document")
        return _stored_case(document, tenant_id=tenant_id, case_id=case_id)

    def save(self, case: Case, *, expected_fingerprint: str | None = None) -> Case:
        ref = self._case_ref(case.tenant_id, case.case_id)
        transaction = self._client.transaction()
        existing = self._read(
            ref.get(transaction=transaction),
            tenant_id=case.tenant_id,
            case_id=case.case_id,
        )
        if existing is None:
            if expected_fingerprint is not None:
                raise CaseStoreConflict("cannot compare an expected version for a new case")
        elif existing.fingerprint() == case.fingerprint():
            return existing
        elif expected_fingerprint is None or existing.fingerprint() != expected_fingerprint:
            raise CaseStoreConflict("case version changed or expected_fingerprint was omitted")
        ref.set(self._document(case), transaction=transaction)
        transaction.commit()
        return case

    def get(self, tenant_id: str, case_id: str) -> Case | None:
        tenant_id = _require(tenant_id, "tenant ID")
        case_id = _require(case_id, "case ID")
        return self._read(
            self._case_ref(tenant_id, case_id).get(),
            tenant_id=tenant_id,
            case_id=case_id,
        )

    def list_tenant(self, tenant_id: str) -> tuple[Case, ...]:
        tenant_id = _require(tenant_id, "tenant ID")
        tenant_ref = self._client.collection(self._root_collection).document(_firestore_id(tenant_id, "tenant ID"))
        cases = [
            case
            for snapshot in tenant_ref.collection("cases").stream()
            if (case := self._read(snapshot, tenant_id=tenant_id, case_id=_case_id_from_snapshot(snapshot))) is not None
        ]
        return tuple(sorted(cases, key=lambda item: item.case_id))

    def count(self) -> int:
        return sum(1 for _ in self._client.collection_group("cases").stream())


def _case_id_from_snapshot(snapshot: _DocumentSnapshot) -> str:
    document = snapshot.to_dict()
    if document is None or not isinstance(document.get("case_id"), str):
        raise ValueError("Firestore case document is missing case_id")
    return cast(str, document["case_id"])
