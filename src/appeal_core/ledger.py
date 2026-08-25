"""Append-only, hash-chained action receipts.

The ledger stores references and decisions, not clinical content. Verification
recomputes every entry from disk and fails on any altered, reordered, malformed,
or duplicated receipt.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import re
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, TextIO, cast

from .state_machine import Actor, DecisionSource, EvidenceRef


JsonPrimitive = None | bool | int | float | str
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]
ReceiptOutcome = Literal["allowed", "denied", "failed", "refused"]

GENESIS_HASH: Final[str] = "0" * 64
SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


class LedgerError(ValueError):
    """Base class for ledger errors."""


class LedgerIntegrityError(LedgerError):
    """Raised when a receipt chain cannot be verified."""


class ReceiptIdempotencyConflict(LedgerError):
    """Raised when a replay key is reused for another action."""


def _require(value: str, label: str) -> str:
    if not value.strip():
        raise LedgerError(f"{label} must not be empty")
    return value


def _utc(value: datetime, label: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise LedgerError(f"{label} must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical(value: JsonObject) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _object(value: JsonValue | None, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise LedgerIntegrityError(f"{label} is not an object")
    return value


def _string(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str):
        raise LedgerIntegrityError(f"{label} is not a string")
    return value


def _evidence_json(ref: EvidenceRef) -> JsonObject:
    return {"kind": ref.kind, "uri": ref.uri, "sha256": ref.sha256}


@dataclass(frozen=True)
class ReceiptDraft:
    receipt_id: str
    recorded_at: datetime
    tenant_id: str
    case_id: str
    actor: Actor
    action: str
    decision_source: DecisionSource
    evidence_refs: tuple[EvidenceRef, ...]
    outcome: ReceiptOutcome
    reason: str
    idempotency_key: str
    refusal_reason: str | None = None

    def __post_init__(self) -> None:
        _require(self.receipt_id, "receipt ID")
        _require(self.tenant_id, "tenant ID")
        _require(self.case_id, "case ID")
        _require(self.action, "action")
        _require(self.reason, "reason")
        _require(self.idempotency_key, "idempotency key")
        _utc(self.recorded_at, "recorded_at")
        if self.outcome == "refused":
            if self.refusal_reason is None or not self.refusal_reason.strip():
                raise LedgerError("refused receipts require refusal_reason")
        elif self.refusal_reason is not None:
            raise LedgerError("refusal_reason is only valid for refused receipts")

    def body(self, previous_hash: str) -> JsonObject:
        return {
            "schema_version": "0.1",
            "receipt_id": self.receipt_id,
            "recorded_at": _utc(self.recorded_at, "recorded_at"),
            "tenant_id": self.tenant_id,
            "case_id": self.case_id,
            "actor": {"identity": self.actor.identity, "kind": self.actor.kind.value},
            "action": self.action,
            "decision_source": {
                "kind": self.decision_source.kind,
                "identifier": self.decision_source.identifier,
                "version": self.decision_source.version,
            },
            "evidence_refs": [_evidence_json(ref) for ref in self.evidence_refs],
            "outcome": self.outcome,
            "reason": self.reason,
            "idempotency_key": self.idempotency_key,
            "refusal_reason": self.refusal_reason,
            "previous_hash": previous_hash,
        }


@dataclass(frozen=True)
class LedgerEntry:
    body: JsonObject
    entry_hash: str

    @property
    def receipt_id(self) -> str:
        return _string(self.body.get("receipt_id"), "receipt_id")

    @property
    def idempotency_key(self) -> str:
        return _string(self.body.get("idempotency_key"), "idempotency_key")

    def serialized(self) -> str:
        full: JsonObject = dict(self.body)
        full["entry_hash"] = self.entry_hash
        return _canonical(full)


@dataclass(frozen=True)
class VerificationResult:
    entry_count: int
    tip_hash: str


def _entry_from_json(value: JsonObject, line_number: int) -> LedgerEntry:
    entry_hash = _string(value.get("entry_hash"), f"line {line_number} entry_hash")
    if not SHA256_PATTERN.fullmatch(entry_hash):
        raise LedgerIntegrityError(f"line {line_number} contains an invalid entry_hash")
    body = dict(value)
    del body["entry_hash"]
    expected = _hash(_canonical(body))
    if expected != entry_hash:
        raise LedgerIntegrityError(f"line {line_number} entry_hash does not match its body")
    _require(_string(body.get("receipt_id"), f"line {line_number} receipt_id"), "receipt ID")
    _require(_string(body.get("idempotency_key"), f"line {line_number} idempotency_key"), "idempotency key")
    return LedgerEntry(body, entry_hash)


def _read_entries(handle: TextIO) -> list[LedgerEntry]:
    handle.seek(0)
    entries: list[LedgerEntry] = []
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    previous_hash = GENESIS_HASH
    for line_number, raw_line in enumerate(handle, start=1):
        line = raw_line.strip()
        if not line:
            raise LedgerIntegrityError(f"line {line_number} is empty")
        try:
            raw: object = json.loads(line)
        except json.JSONDecodeError as error:
            raise LedgerIntegrityError(f"line {line_number} is not valid JSON") from error
        entry = _entry_from_json(_object(cast(JsonValue, raw), f"line {line_number}"), line_number)
        actual_previous = _string(entry.body.get("previous_hash"), f"line {line_number} previous_hash")
        if actual_previous != previous_hash:
            raise LedgerIntegrityError(f"line {line_number} breaks the previous-hash chain")
        if entry.receipt_id in seen_ids:
            raise LedgerIntegrityError(f"duplicate receipt_id at line {line_number}")
        if entry.idempotency_key in seen_keys:
            raise LedgerIntegrityError(f"duplicate idempotency_key at line {line_number}")
        seen_ids.add(entry.receipt_id)
        seen_keys.add(entry.idempotency_key)
        entries.append(entry)
        previous_hash = entry.entry_hash
    return entries
class ReceiptLedger:
    """A POSIX-locked append-only JSONL receipt ledger."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, draft: ReceiptDraft) -> LedgerEntry:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                entries = _read_entries(handle)
                for existing in entries:
                    if existing.idempotency_key == draft.idempotency_key:
                        if existing.body == draft.body(_string(existing.body.get("previous_hash"), "previous_hash")):
                            return existing
                        raise ReceiptIdempotencyConflict(
                            f"idempotency key {draft.idempotency_key!r} was already used for another receipt"
                        )
                previous_hash = entries[-1].entry_hash if entries else GENESIS_HASH
                body = draft.body(previous_hash)
                entry_hash = _hash(_canonical(body))
                entry = LedgerEntry(body, entry_hash)
                handle.seek(0, os.SEEK_END)
                handle.write(entry.serialized() + "\n")
                handle.flush()
                os.fsync(handle.fileno())
                return entry
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def verify(self) -> VerificationResult:
        if not self.path.is_file():
            raise LedgerIntegrityError(f"ledger does not exist: {self.path}")
        with self.path.open("r", encoding="utf-8") as handle:
            entries = _read_entries(handle)
        tip_hash = entries[-1].entry_hash if entries else GENESIS_HASH
        return VerificationResult(len(entries), tip_hash)
