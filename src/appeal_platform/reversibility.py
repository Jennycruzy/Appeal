"""Append-only local journal of actions and their compensating actions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum


GENESIS_HASH = "0" * 64


class ReversibilityConflict(ValueError):
    """Raised when an action or compensation idempotency key changes intent."""


class ActionStatus(str, Enum):
    ACTIVE = "active"
    COMPENSATED = "compensated"


def _require(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class ReversibleAction:
    action_id: str
    tenant_id: str
    case_id: str
    action_kind: str
    idempotency_key: str
    performed_at: datetime
    external_reference: str
    compensating_action: str

    def __post_init__(self) -> None:
        for value, label in [
            (self.action_id, "action ID"),
            (self.tenant_id, "action tenant ID"),
            (self.case_id, "action case ID"),
            (self.action_kind, "action kind"),
            (self.idempotency_key, "action idempotency key"),
            (self.external_reference, "external reference"),
            (self.compensating_action, "compensating action"),
        ]:
            _require(value, label)
        _utc(self.performed_at, "action performed_at")


@dataclass(frozen=True)
class ReversibilityEntry:
    sequence: int
    entry_kind: str
    action_id: str
    tenant_id: str
    case_id: str
    action_kind: str
    idempotency_key: str
    recorded_at: datetime
    external_reference: str
    compensating_action: str
    status: ActionStatus
    actor: str
    previous_hash: str
    entry_hash: str

    def body(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "entry_kind": self.entry_kind,
            "action_id": self.action_id,
            "tenant_id": self.tenant_id,
            "case_id": self.case_id,
            "action_kind": self.action_kind,
            "idempotency_key": self.idempotency_key,
            "recorded_at": self.recorded_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "external_reference": self.external_reference,
            "compensating_action": self.compensating_action,
            "status": self.status.value,
            "actor": self.actor,
            "previous_hash": self.previous_hash,
        }

    def to_json(self) -> dict[str, object]:
        value = self.body()
        value["entry_hash"] = self.entry_hash
        return value


@dataclass(frozen=True)
class ReversibilityVerification:
    entry_count: int
    tip_hash: str


def _hash(body: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class ReversibilityLedger:
    """In-memory hash-chained journal; deployment will persist the same shape."""

    def __init__(self) -> None:
        self._entries: list[ReversibilityEntry] = []
        self._actions: dict[str, ReversibleAction] = {}
        self._entry_by_key: dict[str, ReversibilityEntry] = {}
        self._compensations: dict[str, ReversibilityEntry] = {}

    def _append(
        self,
        *,
        entry_kind: str,
        action: ReversibleAction,
        idempotency_key: str,
        recorded_at: datetime,
        status: ActionStatus,
        actor: str,
    ) -> ReversibilityEntry:
        previous_hash = self._entries[-1].entry_hash if self._entries else GENESIS_HASH
        entry = ReversibilityEntry(
            sequence=len(self._entries) + 1,
            entry_kind=entry_kind,
            action_id=action.action_id,
            tenant_id=action.tenant_id,
            case_id=action.case_id,
            action_kind=action.action_kind,
            idempotency_key=idempotency_key,
            recorded_at=_utc(recorded_at, "reversibility recorded_at"),
            external_reference=action.external_reference,
            compensating_action=action.compensating_action,
            status=status,
            actor=_require(actor, "reversibility actor"),
            previous_hash=previous_hash,
            entry_hash="",
        )
        finalized = replace(entry, entry_hash=_hash(entry.body()))
        self._entries.append(finalized)
        self._entry_by_key[idempotency_key] = finalized
        return finalized

    def record_action(self, action: ReversibleAction) -> ReversibilityEntry:
        existing = self._actions.get(action.action_id)
        if existing is not None:
            if existing != action:
                raise ReversibilityConflict("action ID was reused with different action data")
            return self._entry_by_key[action.idempotency_key]
        existing_key = self._entry_by_key.get(action.idempotency_key)
        if existing_key is not None:
            raise ReversibilityConflict("action idempotency key was already used")
        self._actions[action.action_id] = action
        return self._append(
            entry_kind="action",
            action=action,
            idempotency_key=action.idempotency_key,
            recorded_at=action.performed_at,
            status=ActionStatus.ACTIVE,
            actor="submission_gate",
        )

    def compensate(self, action_id: str, at: datetime, actor: str) -> ReversibilityEntry:
        action = self._actions.get(_require(action_id, "action ID"))
        if action is None:
            raise KeyError(f"unknown reversible action {action_id!r}")
        existing = self._compensations.get(action.action_id)
        if existing is not None:
            return existing
        idempotency_key = f"{action.action_id}:compensate"
        existing_key = self._entry_by_key.get(idempotency_key)
        if existing_key is not None:
            self._compensations[action.action_id] = existing_key
            return existing_key
        entry = self._append(
            entry_kind="compensation",
            action=action,
            idempotency_key=idempotency_key,
            recorded_at=at,
            status=ActionStatus.COMPENSATED,
            actor=actor,
        )
        self._compensations[action.action_id] = entry
        return entry

    def status_for(self, action_id: str) -> ActionStatus:
        action_id = _require(action_id, "action ID")
        if action_id not in self._actions:
            raise KeyError(f"unknown reversible action {action_id!r}")
        return ActionStatus.COMPENSATED if action_id in self._compensations else ActionStatus.ACTIVE

    def entries(self) -> tuple[ReversibilityEntry, ...]:
        return tuple(self._entries)

    def verify(self) -> ReversibilityVerification:
        previous_hash = GENESIS_HASH
        for expected_sequence, entry in enumerate(self._entries, start=1):
            if entry.sequence != expected_sequence or entry.previous_hash != previous_hash:
                raise ReversibilityConflict("reversibility chain order or previous hash is invalid")
            if _hash(entry.body()) != entry.entry_hash:
                raise ReversibilityConflict("reversibility entry hash is invalid")
            previous_hash = entry.entry_hash
        return ReversibilityVerification(len(self._entries), previous_hash)

    def to_public_json(self) -> dict[str, object]:
        verification = self.verify()
        return {
            "entry_count": verification.entry_count,
            "tip_hash": verification.tip_hash,
            "entries": [entry.to_json() for entry in self._entries],
        }
