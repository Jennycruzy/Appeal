"""A reference-only local event spine with duplicate-delivery handling."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Final, Mapping, TypeAlias


EventScalar: TypeAlias = str | int | bool | None
EventPayload: TypeAlias = tuple[tuple[str, EventScalar], ...]
EventHandler: TypeAlias = Callable[["DomainEvent"], None]

_FORBIDDEN_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(
    {"body", "chart", "content", "document", "patient", "prompt", "prose", "raw", "text"}
)


class EventIdempotencyConflict(ValueError):
    """Raised when a scoped event idempotency key changes its intent."""


def _require(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


def _payload(mapping: Mapping[str, EventScalar]) -> EventPayload:
    normalized: list[tuple[str, EventScalar]] = []
    for key, value in sorted(mapping.items()):
        _require(key, "event payload key")
        if key.lower() in _FORBIDDEN_PAYLOAD_KEYS:
            raise ValueError(f"event payload cannot carry raw field {key!r}")
        if value is not None and not isinstance(value, (str, int, bool)):
            raise ValueError("event payload values must be scalar metadata")
        if isinstance(value, str) and len(value) > 512:
            raise ValueError("event payload values must be bounded metadata")
        normalized.append((key, value))
    return tuple(normalized)


def _event_hash(
    tenant_id: str,
    case_id: str,
    topic: str,
    idempotency_key: str,
    payload: EventPayload,
) -> str:
    canonical = json.dumps(
        {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "topic": topic,
            "idempotency_key": idempotency_key,
            "payload": list(payload),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DomainEvent:
    """An event carrying identifiers and references, never clinical content."""

    event_id: str
    tenant_id: str
    case_id: str
    topic: str
    idempotency_key: str
    published_at: datetime
    payload: EventPayload

    def __post_init__(self) -> None:
        _require(self.event_id, "event ID")
        _require(self.tenant_id, "event tenant ID")
        _require(self.case_id, "event case ID")
        _require(self.topic, "event topic")
        _require(self.idempotency_key, "event idempotency key")
        _utc(self.published_at, "event published_at")
        normalized_payload = _payload(dict(self.payload))
        if normalized_payload != self.payload:
            raise ValueError("event payload must be sorted and contain unique keys")
        expected = _event_hash(
            self.tenant_id,
            self.case_id,
            self.topic,
            self.idempotency_key,
            self.payload,
        )
        if self.event_id != expected:
            raise ValueError("event_id does not match the reference-only event body")

    @classmethod
    def create(
        cls,
        tenant_id: str,
        case_id: str,
        topic: str,
        idempotency_key: str,
        published_at: datetime,
        payload: Mapping[str, EventScalar],
    ) -> "DomainEvent":
        tenant_id = _require(tenant_id, "event tenant ID")
        case_id = _require(case_id, "event case ID")
        topic = _require(topic, "event topic")
        idempotency_key = _require(idempotency_key, "event idempotency key")
        normalized = _payload(payload)
        return cls(
            event_id=_event_hash(tenant_id, case_id, topic, idempotency_key, normalized),
            tenant_id=tenant_id,
            case_id=case_id,
            topic=topic,
            idempotency_key=idempotency_key,
            published_at=_utc(published_at, "event published_at"),
            payload=normalized,
        )

    @property
    def scope_idempotency_key(self) -> tuple[str, str, str, str]:
        return self.tenant_id, self.case_id, self.topic, self.idempotency_key

    def payload_dict(self) -> dict[str, EventScalar]:
        return dict(self.payload)

    def to_json(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "case_id": self.case_id,
            "topic": self.topic,
            "idempotency_key": self.idempotency_key,
            "published_at": self.published_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "payload": self.payload_dict(),
        }


@dataclass(frozen=True)
class DeliveryReceipt:
    event_id: str
    handler: str
    status: str
    delivered_at: datetime
    error_type: str | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "handler": self.handler,
            "status": self.status,
            "delivered_at": self.delivered_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "error_type": self.error_type,
        }


class LocalEventSpine:
    """A tiny Pub/Sub-shaped spine with per-handler delivery idempotency."""

    def __init__(self) -> None:
        self._events: dict[str, DomainEvent] = {}
        self._event_by_scope_key: dict[tuple[str, str, str, str], str] = {}
        self._handlers: dict[str, dict[str, EventHandler]] = {}
        self._delivered: set[tuple[str, str]] = set()
        self._receipts: list[DeliveryReceipt] = []

    def subscribe(self, topic: str, handler_name: str, handler: EventHandler) -> None:
        _require(topic, "event topic")
        _require(handler_name, "event handler name")
        handlers = self._handlers.setdefault(topic, {})
        if handler_name in handlers:
            raise ValueError(f"handler {handler_name!r} is already subscribed to {topic!r}")
        handlers[handler_name] = handler

    def publish(self, event: DomainEvent) -> DomainEvent:
        existing = self._events.get(event.event_id)
        if existing is not None:
            if existing != event:
                raise EventIdempotencyConflict("event ID was reused with different event data")
            return existing
        scope_key = event.scope_idempotency_key
        existing_id = self._event_by_scope_key.get(scope_key)
        if existing_id is not None and existing_id != event.event_id:
            raise EventIdempotencyConflict("event idempotency key was reused with different event data")
        self._events[event.event_id] = event
        self._event_by_scope_key[scope_key] = event.event_id
        return event

    def deliver(self, event_id: str | None = None, *, at: datetime | None = None) -> tuple[DeliveryReceipt, ...]:
        delivered_at = _utc(at or datetime.now(UTC), "delivery time")
        if event_id is None:
            events = tuple(self._events.values())
        else:
            event = self._events.get(event_id)
            if event is None:
                raise KeyError(f"unknown event {event_id!r}")
            events = (event,)
        receipts: list[DeliveryReceipt] = []
        for event in events:
            for handler_name, handler in self._handlers.get(event.topic, {}).items():
                delivery_key = (handler_name, event.event_id)
                if delivery_key in self._delivered:
                    receipt = DeliveryReceipt(event.event_id, handler_name, "duplicate", delivered_at)
                    self._receipts.append(receipt)
                    receipts.append(receipt)
                    continue
                try:
                    handler(event)
                except Exception as error:  # pragma: no cover - exercised by integration callers
                    receipt = DeliveryReceipt(event.event_id, handler_name, "failed", delivered_at, type(error).__name__)
                    self._receipts.append(receipt)
                    receipts.append(receipt)
                    continue
                self._delivered.add(delivery_key)
                receipt = DeliveryReceipt(event.event_id, handler_name, "delivered", delivered_at)
                self._receipts.append(receipt)
                receipts.append(receipt)
        return tuple(receipts)

    def events(self) -> tuple[DomainEvent, ...]:
        return tuple(self._events.values())

    def delivery_receipts(self) -> tuple[DeliveryReceipt, ...]:
        return tuple(self._receipts)
