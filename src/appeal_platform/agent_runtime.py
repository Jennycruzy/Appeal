"""Controlled Pub/Sub delivery into a managed Agent Runtime application.

The subscriber is deliberately narrower than the event spine.  It accepts only
one synthetic workflow checkpoint, sends reference metadata rather than case
content, and records invocation state separately from the Pub/Sub event
registration so duplicate pushes do not re-run the managed graph.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, Callable, Mapping
import hashlib
import importlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol, cast

from .events import DomainEvent, EventIdempotencyConflict


TRIGGER_TOPIC = "appeal.workflow.event"
TRIGGER_AGENT = "intake"
TRIGGER_STATUS = "clear"
_MAX_AUTHOR_LENGTH = 128


class AgentRuntimeInvocationInProgress(RuntimeError):
    """Raised when another delivery currently owns the invocation lease."""


class AgentRuntimeQueryError(RuntimeError):
    """Raised when Agent Runtime emits an error event for a query."""

    def __init__(self, error_code: str) -> None:
        self.error_code = _require(error_code, "Agent Runtime query error code")
        super().__init__(f"managed Agent Runtime query failed: {self.error_code}")


class InvocationClaim(str, Enum):
    CLAIMED = "claimed"
    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"


@dataclass(frozen=True)
class AgentRuntimeInvocation:
    """Aggregate-only result from one managed Agent Runtime query."""

    event_id: str
    status: str
    query_event_count: int = 0
    query_authors: tuple[str, ...] = ()
    completed_at: datetime | None = None
    error_type: str | None = None

    def to_public_json(self) -> dict[str, object]:
        return {
            "status": self.status,
            "event_id": self.event_id,
            "query_event_count": self.query_event_count,
            "query_authors": list(self.query_authors),
        }


class AgentRuntimeInvoker(Protocol):
    def invoke(self, event: DomainEvent) -> AgentRuntimeInvocation: ...


class AgentRuntimeInvocationStore(Protocol):
    def claim(self, event: DomainEvent, *, at: datetime) -> InvocationClaim: ...

    def complete(
        self,
        event: DomainEvent,
        invocation: AgentRuntimeInvocation,
        *,
        at: datetime,
    ) -> None: ...

    def fail(self, event: DomainEvent, error_type: str, *, at: datetime) -> None: ...


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


def _parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO-8601 datetime")
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")), label)
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO-8601 datetime") from error


def _event_scope_digest(event: DomainEvent) -> str:
    return hashlib.sha256(
        f"{event.tenant_id}:{event.case_id}".encode("utf-8")
    ).hexdigest()


def _trigger_reason(
    event: DomainEvent,
    *,
    synthetic_only: bool,
    tenant_prefix: str,
    case_prefix: str,
) -> str | None:
    if event.topic != TRIGGER_TOPIC:
        return "event_topic_not_allowlisted"
    payload = event.payload_dict()
    if payload.get("agent") != TRIGGER_AGENT or payload.get("status") != TRIGGER_STATUS:
        return "event_checkpoint_not_allowlisted"
    evidence_ref_count = payload.get("evidence_ref_count")
    if not isinstance(evidence_ref_count, int) or isinstance(evidence_ref_count, bool):
        return "event_metadata_invalid"
    if evidence_ref_count < 0:
        return "event_metadata_invalid"
    if synthetic_only:
        if not event.tenant_id.startswith(tenant_prefix):
            return "synthetic_tenant_scope_rejected"
        if not event.case_id.startswith(case_prefix):
            return "synthetic_case_scope_rejected"
    return None


class LocalAgentRuntimeInvocationStore:
    """In-memory invocation claims used by local tests and rehearsal runs."""

    def __init__(self, *, claim_lease_seconds: float = 120) -> None:
        if claim_lease_seconds <= 0:
            raise ValueError("claim_lease_seconds must be positive")
        self.claim_lease_seconds = claim_lease_seconds
        self._records: dict[str, dict[str, object]] = {}

    def claim(self, event: DomainEvent, *, at: datetime) -> InvocationClaim:
        now = _utc(at, "invocation claim time")
        record = self._records.get(event.event_id)
        if record is None:
            self._records[event.event_id] = {
                "event_id": event.event_id,
                "tenant_id": event.tenant_id,
                "case_id": event.case_id,
                "status": "pending",
                "claimed_at": now,
                "attempt": 1,
            }
            return InvocationClaim.CLAIMED
        self._validate_record(record, event)
        status = record.get("status")
        if status == "completed":
            return InvocationClaim.COMPLETED
        if status == "pending":
            claimed_at = record.get("claimed_at")
            if isinstance(claimed_at, datetime):
                age = (now - _utc(claimed_at, "stored invocation claim time")).total_seconds()
                if age < self.claim_lease_seconds:
                    return InvocationClaim.IN_PROGRESS
            attempt = record.get("attempt")
            if not isinstance(attempt, int) or isinstance(attempt, bool):
                raise EventIdempotencyConflict("stored Agent Runtime invocation attempt is invalid")
            record["claimed_at"] = now
            record["attempt"] = attempt + 1
            return InvocationClaim.CLAIMED
        if status == "failed":
            attempt = record.get("attempt")
            if not isinstance(attempt, int) or isinstance(attempt, bool):
                raise EventIdempotencyConflict("stored Agent Runtime invocation attempt is invalid")
            record["status"] = "pending"
            record["claimed_at"] = now
            record["attempt"] = attempt + 1
            return InvocationClaim.CLAIMED
        raise EventIdempotencyConflict("stored Agent Runtime invocation has an unknown status")

    def complete(
        self,
        event: DomainEvent,
        invocation: AgentRuntimeInvocation,
        *,
        at: datetime,
    ) -> None:
        record = self._records.get(event.event_id)
        if record is None:
            raise EventIdempotencyConflict("Agent Runtime invocation was not claimed")
        self._validate_record(record, event)
        record.update(
            {
                "status": "completed",
                "completed_at": _utc(at, "invocation completion time"),
                "query_event_count": invocation.query_event_count,
                "query_authors": list(invocation.query_authors),
            }
        )

    def fail(self, event: DomainEvent, error_type: str, *, at: datetime) -> None:
        record = self._records.get(event.event_id)
        if record is None:
            raise EventIdempotencyConflict("Agent Runtime invocation was not claimed")
        self._validate_record(record, event)
        record.update(
            {
                "status": "failed",
                "failed_at": _utc(at, "invocation failure time"),
                "error_type": _require(error_type, "invocation error type"),
            }
        )

    @staticmethod
    def _validate_record(record: Mapping[str, object], event: DomainEvent) -> None:
        if (
            record.get("event_id") != event.event_id
            or record.get("tenant_id") != event.tenant_id
            or record.get("case_id") != event.case_id
        ):
            raise EventIdempotencyConflict(
                "Agent Runtime invocation ID was reused with different event data"
            )


class ManagedAgentRuntimeInvoker:
    """Query one existing Agent Runtime resource without persisting responses."""

    def __init__(
        self,
        *,
        resource_name: str,
        project: str,
        location: str,
        client: object | None = None,
        agent: object | None = None,
        user_id_prefix: str = "appeal-pubsub",
        timeout_seconds: float = 45,
    ) -> None:
        self.resource_name = _require(resource_name, "Agent Runtime resource name")
        self.project = _require(project, "Agent Runtime project")
        self.location = _require(location, "Agent Runtime location")
        self.user_id_prefix = _require(user_id_prefix, "Agent Runtime user ID prefix")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds
        self._client = client
        self._agent = agent

    def invoke(self, event: DomainEvent) -> AgentRuntimeInvocation:
        return asyncio.run(self._invoke_async(event))

    async def _invoke_async(self, event: DomainEvent) -> AgentRuntimeInvocation:
        remote_agent = self._remote_agent()
        method = getattr(remote_agent, "async_stream_query", None)
        if not callable(method):
            raise RuntimeError("managed Agent Runtime does not expose async_stream_query")

        async def collect() -> tuple[int, tuple[str, ...]]:
            stream = method(
                user_id=self._user_id(event),
                message=self._message(event),
            )
            if not isinstance(stream, AsyncIterable):
                raise TypeError("managed Agent Runtime query did not return an async stream")
            event_count = 0
            authors: set[str] = set()
            async for response_event in stream:
                event_count += 1
                error_code = self._event_error_code(response_event)
                if error_code is not None:
                    raise AgentRuntimeQueryError(error_code)
                author = self._event_author(response_event)
                if author is not None:
                    authors.add(author)
            return event_count, tuple(sorted(authors))

        event_count, authors = await asyncio.wait_for(collect(), timeout=self.timeout_seconds)
        return AgentRuntimeInvocation(
            event_id=event.event_id,
            status="completed",
            query_event_count=event_count,
            query_authors=authors,
            completed_at=datetime.now(UTC),
        )

    def _remote_agent(self) -> object:
        if self._agent is not None:
            return self._agent
        if self._client is None:
            try:
                vertexai = importlib.import_module("vertexai")
                client_factory = cast(Callable[..., object], getattr(vertexai, "Client"))
                self._client = client_factory(
                    project=self.project,
                    location=self.location,
                    http_options={"api_version": "v1beta1"},
                )
            except (ImportError, AttributeError) as error:
                raise RuntimeError(
                    "managed Agent Runtime invocation requires google-cloud-aiplatform[agent_engines]"
                ) from error
        agent_engines = getattr(self._client, "agent_engines", None)
        getter = getattr(agent_engines, "get", None)
        if not callable(getter):
            raise RuntimeError("Vertex AI client does not expose agent_engines.get")
        self._agent = cast(object, getter(name=self.resource_name))
        return self._agent

    def _message(self, event: DomainEvent) -> str:
        payload = event.payload_dict()
        metadata = {
            "event_id": event.event_id,
            "scope_digest": _event_scope_digest(event),
            "topic": event.topic,
            "agent": payload["agent"],
            "status": payload["status"],
            "evidence_ref_count": payload["evidence_ref_count"],
        }
        return (
            "Controlled synthetic Appeal workflow checkpoint. The JSON below is "
            "reference metadata only; it contains no patient, denial, chart, "
            "policy, payer, or approval content. Return one concise advisory "
            "note. Do not approve, file, mutate an external system, or infer "
            "missing case facts.\n"
            "metadata="
            + json.dumps(metadata, sort_keys=True, separators=(",", ":"))
        )

    def _user_id(self, event: DomainEvent) -> str:
        return f"{self.user_id_prefix}-{event.event_id[:32]}"

    @staticmethod
    def _event_author(value: object) -> str | None:
        if isinstance(value, Mapping):
            author = value.get("author")
        else:
            author = getattr(value, "author", None)
        if not isinstance(author, str) or not author:
            return None
        return author[:_MAX_AUTHOR_LENGTH]

    @staticmethod
    def _event_error_code(value: object) -> str | None:
        if isinstance(value, Mapping):
            error_code = value.get("error_code")
        else:
            error_code = getattr(value, "error_code", None)
        if not isinstance(error_code, str) or not error_code:
            return None
        return error_code[:_MAX_AUTHOR_LENGTH]


class AgentRuntimeSubscriber:
    """Apply the allowlist and idempotency gate around a managed invoker."""

    def __init__(
        self,
        invoker: AgentRuntimeInvoker,
        store: AgentRuntimeInvocationStore,
        *,
        synthetic_only: bool = True,
        tenant_prefix: str = "tenant-demo",
        case_prefix: str = "case-demo",
    ) -> None:
        self.invoker = invoker
        self.store = store
        self.synthetic_only = synthetic_only
        self.tenant_prefix = _require(tenant_prefix, "synthetic tenant prefix")
        self.case_prefix = _require(case_prefix, "synthetic case prefix")

    def handle(
        self,
        event: DomainEvent,
        *,
        at: datetime | None = None,
    ) -> dict[str, object]:
        now = _utc(at or datetime.now(UTC), "Agent Runtime delivery time")
        reason = _trigger_reason(
            event,
            synthetic_only=self.synthetic_only,
            tenant_prefix=self.tenant_prefix,
            case_prefix=self.case_prefix,
        )
        if reason is not None:
            return {
                "status": "skipped",
                "event_id": event.event_id,
                "reason": reason,
            }

        claim = self.store.claim(event, at=now)
        if claim is InvocationClaim.COMPLETED:
            return {
                "status": "duplicate",
                "event_id": event.event_id,
            }
        if claim is InvocationClaim.IN_PROGRESS:
            raise AgentRuntimeInvocationInProgress(
                "another delivery currently owns the Agent Runtime invocation lease"
            )
        try:
            invocation = self.invoker.invoke(event)
            if invocation.event_id != event.event_id:
                raise EventIdempotencyConflict(
                    "managed Agent Runtime returned a different event ID"
                )
            if invocation.status != "completed":
                raise RuntimeError("managed Agent Runtime invocation did not complete")
        except Exception as error:
            error_type = type(error).__name__
            if isinstance(error, AgentRuntimeQueryError):
                error_type = f"{error_type}:{error.error_code}"
            self.store.fail(event, error_type, at=now)
            raise
        self.store.complete(event, invocation, at=now)
        return invocation.to_public_json()


class _DocumentSnapshot(Protocol):
    @property
    def exists(self) -> bool: ...

    def to_dict(self) -> Mapping[str, object] | None: ...


class _DocumentReference(Protocol):
    def get(self, *, transaction: object | None = None) -> _DocumentSnapshot: ...

    def set(
        self,
        document_data: Mapping[str, object],
        *,
        transaction: object | None = None,
    ) -> object: ...

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


class FirestoreAgentRuntimeInvocationStore:
    """Firestore-backed, lease-based idempotency for managed invocations."""

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str = "(default)",
        root_collection: str = "appeal_tenants",
        client: object | None = None,
        claim_lease_seconds: float = 120,
    ) -> None:
        if claim_lease_seconds <= 0:
            raise ValueError("claim_lease_seconds must be positive")
        transactional: _TransactionalFactory | None = None
        if client is None:
            try:
                firestore = importlib.import_module("google.cloud.firestore")
            except ImportError as error:
                raise RuntimeError(
                    "Agent Runtime invocation storage requires google-cloud-firestore"
                ) from error
            factory = cast(_FirestoreFactory, getattr(firestore, "Client"))
            client = factory(project=project, database=database)
            transactional = cast(_TransactionalFactory, getattr(firestore, "transactional"))
        self._client = cast(_FirestoreClient, client)
        self._transactional = transactional
        self._root_collection = _require(root_collection, "Firestore root collection")
        if "/" in self._root_collection:
            raise ValueError("Firestore root collection must not contain '/'")
        self.claim_lease_seconds = claim_lease_seconds

    def _invocation_ref(self, event: DomainEvent) -> _DocumentReference:
        return (
            self._client.collection(self._root_collection)
            .document(_firestore_id(event.tenant_id, "tenant ID"))
            .collection("cases")
            .document(_firestore_id(event.case_id, "case ID"))
            .collection("agent_runtime_invocations")
            .document(_firestore_id(event.event_id, "event ID"))
        )

    @staticmethod
    def _pending_document(event: DomainEvent, at: datetime, attempt: int) -> dict[str, object]:
        return {
            "schema_version": 1,
            "event_id": event.event_id,
            "tenant_id": event.tenant_id,
            "case_id": event.case_id,
            "status": "pending",
            "claimed_at": _timestamp(at, "invocation claim time"),
            "attempt": attempt,
        }

    def claim(self, event: DomainEvent, *, at: datetime) -> InvocationClaim:
        now = _utc(at, "invocation claim time")
        ref = self._invocation_ref(event)

        def write(transaction: _Transaction) -> tuple[InvocationClaim, bool]:
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                transaction.set(ref, self._pending_document(event, now, 1))
                return InvocationClaim.CLAIMED, True
            document = snapshot.to_dict()
            if document is None:
                raise EventIdempotencyConflict("stored Agent Runtime invocation document is empty")
            self._validate_record(document, event)
            status = document.get("status")
            if status == "completed":
                return InvocationClaim.COMPLETED, False
            attempt = document.get("attempt")
            if not isinstance(attempt, int) or isinstance(attempt, bool):
                raise EventIdempotencyConflict("stored Agent Runtime invocation attempt is invalid")
            if status == "pending":
                claimed_at = _parse_timestamp(document.get("claimed_at"), "stored invocation claim time")
                age = (now - claimed_at).total_seconds()
                if age < self.claim_lease_seconds:
                    return InvocationClaim.IN_PROGRESS, False
            elif status != "failed":
                raise EventIdempotencyConflict("stored Agent Runtime invocation has an unknown status")
            transaction.set(ref, self._pending_document(event, now, attempt + 1))
            return InvocationClaim.CLAIMED, True

        if self._transactional is not None:
            transaction = self._client.transaction()
            wrapped = self._transactional(write)
            return cast(Callable[[_Transaction], tuple[InvocationClaim, bool]], wrapped)(transaction)[0]

        transaction = self._client.transaction()
        transaction.begin()
        claim, changed = write(transaction)
        if changed:
            transaction.commit()
        return claim

    def complete(
        self,
        event: DomainEvent,
        invocation: AgentRuntimeInvocation,
        *,
        at: datetime,
    ) -> None:
        ref = self._invocation_ref(event)
        snapshot = ref.get()
        if not snapshot.exists:
            raise EventIdempotencyConflict("Agent Runtime invocation was not claimed")
        document = snapshot.to_dict()
        if document is None:
            raise EventIdempotencyConflict("stored Agent Runtime invocation document is empty")
        self._validate_record(document, event)
        ref.set(
            {
                **dict(document),
                "status": "completed",
                "completed_at": _timestamp(at, "invocation completion time"),
                "query_event_count": invocation.query_event_count,
                "query_authors": list(invocation.query_authors),
            }
        )

    def fail(self, event: DomainEvent, error_type: str, *, at: datetime) -> None:
        ref = self._invocation_ref(event)
        snapshot = ref.get()
        if not snapshot.exists:
            raise EventIdempotencyConflict("Agent Runtime invocation was not claimed")
        document = snapshot.to_dict()
        if document is None:
            raise EventIdempotencyConflict("stored Agent Runtime invocation document is empty")
        self._validate_record(document, event)
        ref.set(
            {
                **dict(document),
                "status": "failed",
                "failed_at": _timestamp(at, "invocation failure time"),
                "error_type": _require(error_type, "invocation error type"),
            }
        )

    @staticmethod
    def _validate_record(document: Mapping[str, object], event: DomainEvent) -> None:
        if document.get("schema_version") != 1:
            raise EventIdempotencyConflict("unsupported Agent Runtime invocation schema")
        if (
            document.get("event_id") != event.event_id
            or document.get("tenant_id") != event.tenant_id
            or document.get("case_id") != event.case_id
        ):
            raise EventIdempotencyConflict(
                "Agent Runtime invocation ID was reused with different event data"
            )


def _firestore_id(value: str, label: str) -> str:
    value = _require(value, label)
    if "/" in value:
        raise ValueError(f"{label} must not contain '/'")
    return value
