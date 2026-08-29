"""Managed Pub/Sub event spine with Firestore idempotency registration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import importlib
import json
from typing import Protocol, cast

from .events import DomainEvent, EventIdempotencyConflict, LocalEventSpine


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


class _PublishFuture(Protocol):
    def result(self, timeout: float | None = None) -> object: ...


class _Publisher(Protocol):
    def publish(self, topic: str, data: bytes, **attributes: str) -> _PublishFuture: ...

    def topic_path(self, project: str, topic: str) -> str: ...


class _PublisherFactory(Protocol):
    def __call__(self) -> object: ...


def _require(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _firestore_id(value: str, label: str) -> str:
    value = _require(value, label)
    if "/" in value:
        raise ValueError(f"{label} must not contain '/'")
    return value


class FirestorePubSubEventSpine(LocalEventSpine):
    """Publish reference-only events once through Pub/Sub.

    Firestore records an event as pending before the publish and as published
    after the Pub/Sub acknowledgement. A retry of a published event is a
    no-op; a retry of a pending event may publish again, and consumers must use
    the stable event ID for delivery idempotency.
    """

    def __init__(
        self,
        *,
        project: str | None = None,
        topic: str = "appeal-events",
        database: str = "(default)",
        root_collection: str = "appeal_tenants",
        client: object | None = None,
        publisher: object | None = None,
        publish_timeout: float = 30,
    ) -> None:
        transactional: _TransactionalFactory | None = None
        if client is None:
            try:
                firestore = importlib.import_module("google.cloud.firestore")
            except ImportError as error:
                raise RuntimeError("Pub/Sub event delivery requires google-cloud-firestore") from error
            factory = cast(_FirestoreFactory, getattr(firestore, "Client"))
            client = factory(project=project, database=database)
            transactional = cast(_TransactionalFactory, getattr(firestore, "transactional"))
        if publisher is None:
            try:
                pubsub = importlib.import_module("google.cloud.pubsub_v1")
            except ImportError as error:
                raise RuntimeError("Pub/Sub event delivery requires google-cloud-pubsub") from error
            publisher_factory = cast(_PublisherFactory, getattr(pubsub, "PublisherClient"))
            publisher = publisher_factory()
        publisher_client = cast(_Publisher, publisher)
        topic = _require(topic, "Pub/Sub topic")
        if topic.startswith("projects/"):
            topic_path = topic
        else:
            if project is None or not project.strip():
                raise ValueError("Pub/Sub project is required when topic is not a full resource path")
            topic_path = publisher_client.topic_path(project, topic)
        super().__init__()
        self._client = cast(_FirestoreClient, client)
        self._transactional = transactional
        self._publisher = publisher_client
        self._topic_path = topic_path
        self._publish_timeout = publish_timeout
        self._root_collection = _firestore_id(root_collection, "Firestore root collection")

    def _event_ref(self, event: DomainEvent) -> _DocumentReference:
        return (
            self._client.collection(self._root_collection)
            .document(_firestore_id(event.tenant_id, "tenant ID"))
            .collection("cases")
            .document(_firestore_id(event.case_id, "case ID"))
            .collection("events")
            .document(_firestore_id(event.event_id, "event ID"))
        )

    @staticmethod
    def _document(event: DomainEvent, status: str) -> dict[str, object]:
        return {
            "schema_version": 1,
            "tenant_id": event.tenant_id,
            "case_id": event.case_id,
            "event_id": event.event_id,
            "status": status,
            "event": event.to_json(),
        }

    def _claim(self, event: DomainEvent) -> bool:
        ref = self._event_ref(event)

        def write(transaction: _Transaction) -> tuple[bool, bool]:
            snapshot = ref.get(transaction=transaction)
            if snapshot.exists:
                document = snapshot.to_dict()
                if document is None:
                    raise EventIdempotencyConflict("stored Pub/Sub event document is empty")
                if document.get("event_id") != event.event_id or document.get("event") != event.to_json():
                    raise EventIdempotencyConflict("event ID was reused with different event data")
                status = document.get("status")
                if status == "published":
                    return False, False
                if status != "pending":
                    raise EventIdempotencyConflict("stored Pub/Sub event has an unknown status")
                return True, False
            transaction.set(ref, self._document(event, "pending"))
            return True, True

        if self._transactional is not None:
            transaction = self._client.transaction()
            wrapped = self._transactional(write)
            return cast(Callable[[_Transaction], tuple[bool, bool]], wrapped)(transaction)[0]

        transaction = self._client.transaction()
        transaction.begin()
        should_publish, changed = write(transaction)
        if changed:
            transaction.commit()
        return should_publish

    def _mark_published(self, event: DomainEvent) -> None:
        self._event_ref(event).set(self._document(event, "published"))

    def publish(self, event: DomainEvent) -> DomainEvent:
        existing_local = next((item for item in self.events() if item.event_id == event.event_id), None)
        if existing_local is not None:
            if existing_local != event:
                raise EventIdempotencyConflict("event ID was reused with different event data")
            return existing_local
        if not self._claim(event):
            return super().publish(event)
        payload = json.dumps(event.to_json(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        future = self._publisher.publish(
            self._topic_path,
            payload,
            event_id=event.event_id,
            tenant_id=event.tenant_id,
            case_id=event.case_id,
            event_topic=event.topic,
        )
        future.result(timeout=self._publish_timeout)
        self._mark_published(event)
        return super().publish(event)

    def accept(self, event: DomainEvent) -> DomainEvent:
        """Record a Pub/Sub delivery without publishing it back to the topic."""

        existing_local = next((item for item in self.events() if item.event_id == event.event_id), None)
        if existing_local is not None:
            if existing_local != event:
                raise EventIdempotencyConflict("event ID was reused with different event data")
            return existing_local
        ref = self._event_ref(event)
        snapshot = ref.get()
        if snapshot.exists:
            document = snapshot.to_dict()
            if document is None or document.get("event") != event.to_json():
                raise EventIdempotencyConflict("event ID was reused with different event data")
        ref.set(self._document(event, "published"))
        return super().publish(event)
