"""Explicit, immutable case state machine for Appeal.

This module owns workflow order. Models may propose structured work, but they
cannot choose the next state. Every transition is typed, idempotent, and carries
an actor, decision source, deadline key, reason, and evidence references.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Final, Literal, cast


JsonPrimitive = None | bool | int | float | str
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]


class CaseState(str, Enum):
    INTAKE_RECEIVED = "INTAKE_RECEIVED"
    DENIAL_PARSED = "DENIAL_PARSED"
    PARSE_FAILED_HUMAN_REVIEW = "PARSE_FAILED_HUMAN_REVIEW"
    POLICY_LOCATED = "POLICY_LOCATED"
    POLICY_NOT_FOUND_HUMAN_REVIEW = "POLICY_NOT_FOUND_HUMAN_REVIEW"
    CRITERION_IDENTIFIED = "CRITERION_IDENTIFIED"
    EVIDENCE_ASSEMBLED = "EVIDENCE_ASSEMBLED"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
    DRAFT_READY = "DRAFT_READY"
    AWAITING_CLINICIAN = "AWAITING_CLINICIAN"
    DRAFT_REVISION = "DRAFT_REVISION"
    SUBMITTED_LEVEL_1 = "SUBMITTED_LEVEL_1"
    AWAITING_DETERMINATION = "AWAITING_DETERMINATION"
    DETERMINATION_RECEIVED = "DETERMINATION_RECEIVED"
    CLOSED_WON = "CLOSED_WON"
    ESCALATION_ELIGIBLE = "ESCALATION_ELIGIBLE"
    PEER_TO_PEER_REQUESTED = "PEER_TO_PEER_REQUESTED"
    EXTERNAL_REVIEW_FILED = "EXTERNAL_REVIEW_FILED"
    CLOSED_LOST = "CLOSED_LOST"
    CLOSED_ABANDONED_DEADLINE = "CLOSED_ABANDONED_DEADLINE"


class ActorKind(str, Enum):
    AGENT = "agent"
    HUMAN = "human"
    SCHEDULER = "scheduler"
    SYSTEM = "system"


class DeadlineStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    NOT_APPLICABLE = "not_applicable"


DecisionKind = Literal["agent", "human", "deterministic"]


class StateMachineError(ValueError):
    """Base class for fail-closed workflow errors."""


class InvalidTransition(StateMachineError):
    """Raised when a requested transition is not in the explicit graph."""


class SignatureRequired(StateMachineError):
    """Raised when submission is attempted without clinician co-signature."""


class IdempotencyConflict(StateMachineError):
    """Raised when an idempotency key is replayed with different intent."""


class UnverifiedDeadline(StateMachineError):
    """Raised when code attempts to calculate an unverified statutory clock."""


def _require_nonempty(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _require_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


def _json_object(path: Path) -> JsonObject:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"expected a JSON-compatible YAML object in {path}")
    return cast(JsonObject, raw)


def _string(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _object(value: JsonValue | None, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(JsonObject, value)


def _optional_int(value: JsonValue | None, label: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer or null")
    return value


@dataclass(frozen=True)
class Deadline:
    key: str
    status: DeadlineStatus
    duration_seconds: int | None
    unit: str
    citation_url: str
    note: str

    def deadline_at(self, entered_at: datetime) -> datetime | None:
        entered_at = _require_utc(entered_at, "entered_at")
        if self.status is DeadlineStatus.NOT_APPLICABLE:
            return None
        if self.status is not DeadlineStatus.VERIFIED or self.duration_seconds is None:
            raise UnverifiedDeadline(f"deadline {self.key!r} is not verified")
        return entered_at + timedelta(seconds=self.duration_seconds)


class DeadlineCatalog:
    """Validated runtime deadlines loaded from the project configuration."""

    def __init__(self, clocks: dict[str, Deadline], state_deadlines: dict[CaseState, str]) -> None:
        self._clocks = dict(clocks)
        self._state_deadlines = dict(state_deadlines)

    @classmethod
    def from_path(cls, path: Path) -> "DeadlineCatalog":
        document = _json_object(path)
        clocks_object = _object(document.get("clocks"), "clocks")
        clocks: dict[str, Deadline] = {}
        for key, value in clocks_object.items():
            clock = _object(value, f"clocks.{key}")
            status_text = _string(clock.get("status"), f"clocks.{key}.status")
            try:
                status = DeadlineStatus(status_text)
            except ValueError as error:
                raise ValueError(f"unknown deadline status: {status_text}") from error
            duration_seconds = _optional_int(clock.get("duration_seconds"), f"clocks.{key}.duration_seconds")
            if status is DeadlineStatus.VERIFIED and (duration_seconds is None or duration_seconds <= 0):
                raise ValueError(f"verified deadline {key!r} must have a positive duration")
            if status is not DeadlineStatus.VERIFIED and duration_seconds is not None:
                raise ValueError(f"non-verified deadline {key!r} must not have a duration")
            clocks[key] = Deadline(
                key=key,
                status=status,
                duration_seconds=duration_seconds,
                unit=_string(clock.get("unit"), f"clocks.{key}.unit"),
                citation_url=_string(clock.get("citation_url"), f"clocks.{key}.citation_url"),
                note=_string(clock.get("note"), f"clocks.{key}.note"),
            )
        state_object = _object(document.get("state_deadlines"), "state_deadlines")
        state_deadlines: dict[CaseState, str] = {}
        for state_text, key_value in state_object.items():
            try:
                state = CaseState(state_text)
            except ValueError as error:
                raise ValueError(f"unknown case state in deadline config: {state_text}") from error
            key = _string(key_value, f"state_deadlines.{state_text}")
            if key not in clocks:
                raise ValueError(f"state {state_text} references unknown deadline {key}")
            state_deadlines[state] = key
        missing_states = set(CaseState) - set(state_deadlines)
        if missing_states:
            missing = ", ".join(sorted(state.value for state in missing_states))
            raise ValueError(f"deadline config omits states: {missing}")
        return cls(clocks, state_deadlines)

    def for_state(self, state: CaseState) -> Deadline:
        key = self._state_deadlines.get(state)
        if key is None:
            raise InvalidTransition(f"no deadline configured for state {state.value}")
        return self.for_key(key)

    def for_key(self, key: str) -> Deadline:
        deadline = self._clocks.get(key)
        if deadline is None:
            raise InvalidTransition(f"unknown deadline key {key!r}")
        return deadline


@dataclass(frozen=True)
class Actor:
    identity: str
    kind: ActorKind

    def __post_init__(self) -> None:
        _require_nonempty(self.identity, "actor identity")


@dataclass(frozen=True)
class DecisionSource:
    kind: DecisionKind
    identifier: str
    version: str

    def __post_init__(self) -> None:
        _require_nonempty(self.identifier, "decision source identifier")
        _require_nonempty(self.version, "decision source version")


@dataclass(frozen=True)
class EvidenceRef:
    """A reference only; evidence content never travels through this object."""

    kind: str
    uri: str
    sha256: str

    def __post_init__(self) -> None:
        _require_nonempty(self.kind, "evidence kind")
        _require_nonempty(self.uri, "evidence URI")
        _require_nonempty(self.sha256, "evidence SHA-256")


@dataclass(frozen=True)
class StateTransition:
    case_id: str
    tenant_id: str
    from_state: CaseState
    to_state: CaseState
    entered_at: datetime
    actor: Actor
    decision_source: DecisionSource
    deadline_key: str
    reason: str
    evidence_refs: tuple[EvidenceRef, ...]
    idempotency_key: str
    clinician_signature: EvidenceRef | None

    def __post_init__(self) -> None:
        _require_nonempty(self.case_id, "case ID")
        _require_nonempty(self.tenant_id, "tenant ID")
        _require_utc(self.entered_at, "transition entered_at")
        _require_nonempty(self.deadline_key, "deadline key")
        _require_nonempty(self.reason, "transition reason")
        _require_nonempty(self.idempotency_key, "idempotency key")


@dataclass(frozen=True)
class Case:
    case_id: str
    tenant_id: str
    state: CaseState
    entered_at: datetime
    transitions: tuple[StateTransition, ...]

    def __post_init__(self) -> None:
        _require_nonempty(self.case_id, "case ID")
        _require_nonempty(self.tenant_id, "tenant ID")
        _require_utc(self.entered_at, "case entered_at")
        if not self.transitions:
            raise ValueError("a case must contain its initial transition")
        last = self.transitions[-1]
        if last.to_state is not self.state:
            raise ValueError("case state does not match its final transition")
        if last.entered_at != self.entered_at:
            raise ValueError("case entered_at does not match its final transition")

    @property
    def deadline_key(self) -> str:
        return self.transitions[-1].deadline_key

    @property
    def last_transition(self) -> StateTransition:
        return self.transitions[-1]

    def fingerprint(self) -> str:
        canonical = json.dumps(self.to_json(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_json(self) -> JsonObject:
        return {
            "case_id": self.case_id,
            "tenant_id": self.tenant_id,
            "state": self.state.value,
            "entered_at": self.entered_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "transitions": [
                {
                    "case_id": transition.case_id,
                    "tenant_id": transition.tenant_id,
                    "from_state": transition.from_state.value,
                    "to_state": transition.to_state.value,
                    "entered_at": transition.entered_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                    "actor": {"identity": transition.actor.identity, "kind": transition.actor.kind.value},
                    "decision_source": {
                        "kind": transition.decision_source.kind,
                        "identifier": transition.decision_source.identifier,
                        "version": transition.decision_source.version,
                    },
                    "deadline_key": transition.deadline_key,
                    "reason": transition.reason,
                    "evidence_refs": [
                        {"kind": ref.kind, "uri": ref.uri, "sha256": ref.sha256}
                        for ref in transition.evidence_refs
                    ],
                    "idempotency_key": transition.idempotency_key,
                    "clinician_signature": (
                        {
                            "kind": transition.clinician_signature.kind,
                            "uri": transition.clinician_signature.uri,
                            "sha256": transition.clinician_signature.sha256,
                        }
                        if transition.clinician_signature is not None
                        else None
                    ),
                }
                for transition in self.transitions
            ],
        }


ALLOWED_TRANSITIONS: Final[dict[CaseState, frozenset[CaseState]]] = {
    CaseState.INTAKE_RECEIVED: frozenset({CaseState.DENIAL_PARSED, CaseState.PARSE_FAILED_HUMAN_REVIEW}),
    CaseState.DENIAL_PARSED: frozenset({CaseState.POLICY_LOCATED, CaseState.POLICY_NOT_FOUND_HUMAN_REVIEW}),
    CaseState.PARSE_FAILED_HUMAN_REVIEW: frozenset(),
    CaseState.POLICY_LOCATED: frozenset({CaseState.CRITERION_IDENTIFIED}),
    CaseState.POLICY_NOT_FOUND_HUMAN_REVIEW: frozenset(),
    CaseState.CRITERION_IDENTIFIED: frozenset({CaseState.EVIDENCE_ASSEMBLED, CaseState.EVIDENCE_INSUFFICIENT}),
    CaseState.EVIDENCE_ASSEMBLED: frozenset({CaseState.DRAFT_READY}),
    CaseState.EVIDENCE_INSUFFICIENT: frozenset({CaseState.DRAFT_READY, CaseState.CLOSED_ABANDONED_DEADLINE}),
    CaseState.DRAFT_READY: frozenset({CaseState.AWAITING_CLINICIAN}),
    CaseState.AWAITING_CLINICIAN: frozenset({CaseState.DRAFT_REVISION, CaseState.SUBMITTED_LEVEL_1}),
    CaseState.DRAFT_REVISION: frozenset({CaseState.DRAFT_READY, CaseState.AWAITING_CLINICIAN}),
    CaseState.SUBMITTED_LEVEL_1: frozenset({CaseState.AWAITING_DETERMINATION}),
    CaseState.AWAITING_DETERMINATION: frozenset({CaseState.DETERMINATION_RECEIVED, CaseState.CLOSED_ABANDONED_DEADLINE}),
    CaseState.DETERMINATION_RECEIVED: frozenset({CaseState.CLOSED_WON, CaseState.ESCALATION_ELIGIBLE}),
    CaseState.CLOSED_WON: frozenset(),
    CaseState.ESCALATION_ELIGIBLE: frozenset({CaseState.PEER_TO_PEER_REQUESTED, CaseState.CLOSED_ABANDONED_DEADLINE}),
    CaseState.PEER_TO_PEER_REQUESTED: frozenset({CaseState.EXTERNAL_REVIEW_FILED, CaseState.CLOSED_ABANDONED_DEADLINE}),
    CaseState.EXTERNAL_REVIEW_FILED: frozenset({CaseState.CLOSED_WON, CaseState.CLOSED_LOST, CaseState.CLOSED_ABANDONED_DEADLINE}),
    CaseState.CLOSED_LOST: frozenset(),
    CaseState.CLOSED_ABANDONED_DEADLINE: frozenset(),
}


class CaseStateMachine:
    def __init__(self, deadlines: DeadlineCatalog) -> None:
        self._deadlines = deadlines

    def create(self, case_id: str, tenant_id: str, entered_at: datetime, actor: Actor, source: DecisionSource) -> Case:
        entered_at = _require_utc(entered_at, "entered_at")
        deadline = self._deadlines.for_state(CaseState.INTAKE_RECEIVED)
        transition = StateTransition(
            case_id=case_id,
            tenant_id=tenant_id,
            from_state=CaseState.INTAKE_RECEIVED,
            to_state=CaseState.INTAKE_RECEIVED,
            entered_at=entered_at,
            actor=actor,
            decision_source=source,
            deadline_key=deadline.key,
            reason="case created from denial intake",
            evidence_refs=(),
            idempotency_key=f"{case_id}:create",
            clinician_signature=None,
        )
        return Case(case_id, tenant_id, CaseState.INTAKE_RECEIVED, entered_at, (transition,))

    def transition(
        self,
        case: Case,
        to_state: CaseState,
        entered_at: datetime,
        actor: Actor,
        source: DecisionSource,
        reason: str,
        evidence_refs: tuple[EvidenceRef, ...],
        idempotency_key: str,
        clinician_signature: EvidenceRef | None = None,
    ) -> Case:
        entered_at = _require_utc(entered_at, "entered_at")
        previous = next((item for item in case.transitions if item.idempotency_key == idempotency_key), None)
        if previous is not None:
            same_intent = previous.to_state is to_state and previous.reason == reason
            if not same_intent:
                raise IdempotencyConflict(f"idempotency key {idempotency_key!r} was already used for another transition")
            return case
        allowed = ALLOWED_TRANSITIONS[case.state]
        if to_state not in allowed:
            raise InvalidTransition(f"{case.state.value} -> {to_state.value} is not allowed")
        if to_state is CaseState.SUBMITTED_LEVEL_1 and clinician_signature is None:
            raise SignatureRequired("a clinician signature reference is required before submission")
        deadline = self._deadlines.for_state(to_state)
        transition = StateTransition(
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            from_state=case.state,
            to_state=to_state,
            entered_at=entered_at,
            actor=actor,
            decision_source=source,
            deadline_key=deadline.key,
            reason=reason,
            evidence_refs=evidence_refs,
            idempotency_key=idempotency_key,
            clinician_signature=clinician_signature,
        )
        return Case(case.case_id, case.tenant_id, to_state, entered_at, (*case.transitions, transition))

    def deadline_at(self, case: Case) -> datetime | None:
        return self._deadlines.for_key(case.deadline_key).deadline_at(case.entered_at)
