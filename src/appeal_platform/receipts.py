"""Firestore-backed hash-chained action receipts.

The cloud adapter keeps the same receipt body and verification rules as the
local JSONL ledger. Each tenant/case has one serialized chain document so an
append can compare the idempotency key, extend the chain, and commit the new
tip in one Firestore transaction.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import importlib
from typing import Protocol, cast

from appeal_core import (
    GENESIS_HASH,
    LedgerEntry,
    LedgerIntegrityError,
    ReceiptDraft,
    ReceiptIdempotencyConflict,
    ReceiptLedger,
    VerificationResult,
)
from appeal_core.ledger import _canonical, _entry_from_json, _hash
from appeal_core.state_machine import JsonObject


def _require(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _firestore_id(value: str, label: str) -> str:
    value = _require(value, label)
    if "/" in value:
        raise ValueError(f"{label} must not contain '/'")
    return value


class _DocumentSnapshot(Protocol):
    @property
    def exists(self) -> bool: ...

    def to_dict(self) -> Mapping[str, object] | None: ...


class _DocumentReference(Protocol):
    def get(self, *, transaction: object | None = None) -> _DocumentSnapshot: ...

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


def _entry_document(entry: LedgerEntry) -> dict[str, object]:
    document: dict[str, object] = dict(entry.body)
    document["entry_hash"] = entry.entry_hash
    return document


def _read_entries(document: Mapping[str, object] | None, *, tenant_id: str, case_id: str) -> list[LedgerEntry]:
    if document is None:
        return []
    if document.get("schema_version") != 1:
        raise LedgerIntegrityError("unsupported Firestore receipt ledger schema")
    if document.get("tenant_id") != tenant_id or document.get("case_id") != case_id:
        raise LedgerIntegrityError("Firestore receipt ledger identity does not match its path")
    raw_entries = document.get("entries", [])
    if not isinstance(raw_entries, list):
        raise LedgerIntegrityError("Firestore receipt ledger entries must be an array")
    entries: list[LedgerEntry] = []
    seen_receipt_ids: set[str] = set()
    seen_idempotency_keys: set[str] = set()
    previous_hash = GENESIS_HASH
    for index, raw_entry in enumerate(raw_entries, start=1):
        if not isinstance(raw_entry, dict):
            raise LedgerIntegrityError(f"Firestore receipt entry {index} is not an object")
        entry = _entry_from_json(cast(JsonObject, raw_entry), index)
        actual_previous = entry.body.get("previous_hash")
        if actual_previous != previous_hash:
            raise LedgerIntegrityError(f"Firestore receipt entry {index} breaks the previous-hash chain")
        if entry.receipt_id in seen_receipt_ids:
            raise LedgerIntegrityError(f"duplicate receipt_id at Firestore entry {index}")
        if entry.idempotency_key in seen_idempotency_keys:
            raise LedgerIntegrityError(f"duplicate idempotency_key at Firestore entry {index}")
        seen_receipt_ids.add(entry.receipt_id)
        seen_idempotency_keys.add(entry.idempotency_key)
        entries.append(entry)
        previous_hash = entry.entry_hash
    expected_tip = entries[-1].entry_hash if entries else GENESIS_HASH
    if document.get("entry_count") != len(entries):
        raise LedgerIntegrityError("Firestore receipt entry_count does not match its entries")
    if document.get("tip_hash") != expected_tip:
        raise LedgerIntegrityError("Firestore receipt tip_hash does not match its entries")
    return entries


class FirestoreReceiptLedger(ReceiptLedger):
    """A tenant/case-scoped Firestore implementation of ``ReceiptLedger``."""

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
                    "Firestore receipts require the google-cloud-firestore package"
                ) from error
            factory = cast(_FirestoreFactory, getattr(firestore, "Client"))
            client = factory(project=project, database=database)
            transactional = cast(_TransactionalFactory, getattr(firestore, "transactional"))
        self._client = cast(_FirestoreClient, client)
        self._transactional = transactional
        self._root_collection = _firestore_id(root_collection, "Firestore root collection")

    def _ledger_ref(self, tenant_id: str, case_id: str) -> _DocumentReference:
        return (
            self._client.collection(self._root_collection)
            .document(_firestore_id(tenant_id, "tenant ID"))
            .collection("cases")
            .document(_firestore_id(case_id, "case ID"))
            .collection("receipt_ledger")
            .document("current")
        )

    @staticmethod
    def _document(tenant_id: str, case_id: str, entries: list[LedgerEntry]) -> dict[str, object]:
        tip_hash = entries[-1].entry_hash if entries else GENESIS_HASH
        return {
            "schema_version": 1,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "entry_count": len(entries),
            "tip_hash": tip_hash,
            "entries": [_entry_document(entry) for entry in entries],
        }

    def append(self, draft: ReceiptDraft) -> LedgerEntry:
        ref = self._ledger_ref(draft.tenant_id, draft.case_id)

        def write(transaction: _Transaction) -> tuple[LedgerEntry, bool]:
            snapshot = ref.get(transaction=transaction)
            document = snapshot.to_dict() if snapshot.exists else None
            entries = _read_entries(document, tenant_id=draft.tenant_id, case_id=draft.case_id)
            for existing in entries:
                if existing.idempotency_key == draft.idempotency_key:
                    previous_hash = existing.body.get("previous_hash")
                    if not isinstance(previous_hash, str):
                        raise LedgerIntegrityError("receipt previous_hash is not a string")
                    if existing.body == draft.body(previous_hash):
                        return existing, False
                    raise ReceiptIdempotencyConflict(
                        f"idempotency key {draft.idempotency_key!r} was already used for another receipt"
                    )
            previous_hash = entries[-1].entry_hash if entries else GENESIS_HASH
            body = draft.body(previous_hash)
            entry = LedgerEntry(body, _hash(_canonical(body)))
            transaction.set(ref, self._document(draft.tenant_id, draft.case_id, [*entries, entry]))
            return entry, True

        if self._transactional is not None:
            transaction = self._client.transaction()
            wrapped = self._transactional(write)
            entry, _ = cast(Callable[[_Transaction], tuple[LedgerEntry, bool]], wrapped)(transaction)
            return entry

        transaction = self._client.transaction()
        transaction.begin()
        entry, changed = write(transaction)
        if changed:
            transaction.commit()
        return entry

    def verify_scope(self, tenant_id: str, case_id: str) -> VerificationResult:
        tenant_id = _require(tenant_id, "tenant ID")
        case_id = _require(case_id, "case ID")
        snapshot = self._ledger_ref(tenant_id, case_id).get()
        if not snapshot.exists:
            raise LedgerIntegrityError(f"receipt ledger does not exist for {tenant_id}/{case_id}")
        entries = _read_entries(snapshot.to_dict(), tenant_id=tenant_id, case_id=case_id)
        return VerificationResult(len(entries), entries[-1].entry_hash if entries else GENESIS_HASH)

    def verify(self, tenant_id: str | None = None, case_id: str | None = None) -> VerificationResult:
        if tenant_id is None or case_id is None:
            raise LedgerIntegrityError("Firestore receipt verification requires tenant_id and case_id")
        return self.verify_scope(tenant_id, case_id)
