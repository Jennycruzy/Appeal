from __future__ import annotations

import unittest
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from appeal_agents.demo import demo_input
from appeal_core import (
    Actor,
    ActorKind,
    Case,
    CaseState,
    CaseStateMachine,
    DecisionSource,
    DeadlineCatalog,
    LedgerIntegrityError,
)
from appeal_agents import AppealWorkflow
from appeal_platform import (
    CaseStoreConflict,
    FirestoreCaseStore,
    FirestorePubSubEventSpine,
    FirestoreReceiptLedger,
    FirestoreWorkflowPersistence,
    FirestoreWorkflowSessionStore,
    LocalCaseRuntime,
)
from appeal_platform.events import DomainEvent
from appeal_service import LocalAppealService


class FakeSnapshot:
    def __init__(self, document: Mapping[str, object] | None) -> None:
        self._document = dict(document) if document is not None else None

    @property
    def exists(self) -> bool:
        return self._document is not None

    def to_dict(self) -> Mapping[str, object] | None:
        return self._document


class FakeTransaction:
    def __init__(self, client: "FakeFirestoreClient") -> None:
        self.client = client
        self.pending: dict[tuple[str, ...], Mapping[str, object]] = {}

    def begin(self) -> None:
        return

    def set(self, document_ref: FakeDocument, document_data: Mapping[str, object]) -> None:
        self.pending[document_ref.path] = dict(document_data)

    def commit(self) -> None:
        self.client.documents.update(self.pending)


class FakeDocument:
    def __init__(self, client: "FakeFirestoreClient", path: tuple[str, ...]) -> None:
        self.client = client
        self.path = path

    def get(self, *, transaction: object | None = None) -> FakeSnapshot:
        return FakeSnapshot(self.client.documents.get(self.path))

    def set(self, document_data: Mapping[str, object], *, transaction: object | None = None) -> None:
        if isinstance(transaction, FakeTransaction):
            transaction.pending[self.path] = dict(document_data)
        else:
            self.client.documents[self.path] = dict(document_data)

    def collection(self, collection_id: str) -> "FakeCollection":
        return FakeCollection(self.client, (*self.path, collection_id))


class FakeCollection:
    def __init__(self, client: "FakeFirestoreClient", path: tuple[str, ...]) -> None:
        self.client = client
        self.path = path

    def document(self, document_id: str) -> FakeDocument:
        return FakeDocument(self.client, (*self.path, document_id))

    def collection(self, collection_id: str) -> "FakeCollection":
        return FakeCollection(self.client, (*self.path, collection_id))

    def stream(self) -> Iterable[FakeSnapshot]:
        prefix = (*self.path,)
        for path, document in self.client.documents.items():
            if len(path) == len(prefix) + 1 and path[: len(prefix)] == prefix:
                yield FakeSnapshot(document)


class FakeFirestoreClient:
    def __init__(self) -> None:
        self.documents: dict[tuple[str, ...], Mapping[str, object]] = {}

    def collection(self, collection_path: str) -> FakeCollection:
        return FakeCollection(self, (collection_path,))

    def collection_group(self, collection_id: str) -> FakeCollection:
        collection = FakeCollection(self, (collection_id,))
        collection.stream = lambda: (
            FakeSnapshot(document)
            for path, document in self.documents.items()
            if len(path) >= 2 and path[-2] == collection_id
        )
        return collection

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)


class FakePublishFuture:
    def __init__(self, message_id: str) -> None:
        self.message_id = message_id

    def result(self, timeout: float | None = None) -> str:
        return self.message_id


class FakePublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, bytes, dict[str, str]]] = []

    def topic_path(self, project: str, topic: str) -> str:
        return f"projects/{project}/topics/{topic}"

    def publish(self, topic: str, data: bytes, **attributes: str) -> FakePublishFuture:
        self.messages.append((topic, data, attributes))
        return FakePublishFuture(f"message-{len(self.messages)}")


ROOT = Path(__file__).resolve().parents[1]
MACHINE = CaseStateMachine(DeadlineCatalog.from_path(ROOT / "config" / "deadlines.yaml"))
TIME = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
SOURCE = DecisionSource("deterministic", "test", "1")
ACTOR = Actor("test-agent", ActorKind.AGENT)


def make_case(case_id: str) -> Case:
    return MACHINE.create(case_id, "tenant-a", TIME, ACTOR, SOURCE)


class FirestoreStoreTests(unittest.TestCase):
    def test_pubsub_event_spine_is_reference_only_and_idempotent(self) -> None:
        client = FakeFirestoreClient()
        publisher = FakePublisher()
        spine = FirestorePubSubEventSpine(
            project="project-a",
            topic="appeal-events",
            client=client,
            publisher=publisher,
        )
        event = DomainEvent.create(
            "tenant-a",
            "case-a",
            "appeal.workflow.event",
            "case-a:event:1",
            TIME,
            {"agent": "intake", "status": "clear"},
        )
        self.assertEqual(spine.publish(event), event)
        self.assertEqual(spine.publish(DomainEvent.from_json(event.to_json())), event)
        self.assertEqual(len(publisher.messages), 1)
        message_topic, message_body, attributes = publisher.messages[0]
        self.assertEqual(message_topic, "projects/project-a/topics/appeal-events")
        self.assertEqual(attributes["event_id"], event.event_id)
        self.assertNotIn("content", message_body.decode("utf-8"))
        self.assertNotIn("chart", message_body.decode("utf-8"))

        second_spine = FirestorePubSubEventSpine(
            project="project-a",
            topic="appeal-events",
            client=client,
            publisher=publisher,
        )
        second_spine.publish(event)
        second_spine.accept(event)
        self.assertEqual(len(publisher.messages), 1)

        # A Pub/Sub push is already delivered. Accepting it must not publish
        # the same message back to the topic and create a delivery loop.
        third_spine = FirestorePubSubEventSpine(
            project="project-a",
            topic="appeal-events",
            client=client,
            publisher=publisher,
        )
        third_spine.accept(event)
        self.assertEqual(len(publisher.messages), 1)

        with self.assertRaises(ValueError):
            DomainEvent.create(
                "tenant-a",
                "case-a",
                "appeal.workflow.event",
                "case-a:event:2",
                TIME,
                {"content": "raw denial prose"},
            )

    def test_firestore_receipts_are_idempotent_hash_chained_and_content_free(self) -> None:
        client = FakeFirestoreClient()
        ledger = FirestoreReceiptLedger(client=client)
        workflow = AppealWorkflow(MACHINE, ledger=ledger)
        first = workflow.run(demo_input())
        second = workflow.run(demo_input())
        self.assertEqual(first.outcome.value, "awaiting_clinician")
        self.assertEqual(second.outcome.value, "awaiting_clinician")
        verified = ledger.verify_scope("tenant-demo", "case-demo-001")
        self.assertGreater(verified.entry_count, 1)
        receipt_path = (
            "appeal_tenants",
            "tenant-demo",
            "cases",
            "case-demo-001",
            "receipt_ledger",
            "current",
        )
        self.assertNotIn("advanced imaging", str(client.documents[receipt_path]))
        self.assertNotIn("conservative therapy completed", str(client.documents[receipt_path]))
        tampered = dict(client.documents[receipt_path])
        raw_entries = list(tampered["entries"])  # type: ignore[arg-type]
        first_entry = dict(raw_entries[0])
        first_entry["reason"] = "tampered"
        raw_entries[0] = first_entry
        tampered["entries"] = raw_entries
        client.documents[receipt_path] = tampered
        with self.assertRaises(LedgerIntegrityError):
            ledger.verify_scope("tenant-demo", "case-demo-001")

    def test_firestore_round_trip_is_tenant_scoped_and_content_free(self) -> None:
        store = FirestoreCaseStore(client=FakeFirestoreClient())
        case = make_case("case-a")
        store.save(case)

        restored = store.get("tenant-a", "case-a")
        self.assertEqual(restored, case)
        self.assertEqual(store.list_tenant("tenant-a"), (case,))
        self.assertEqual(store.list_tenant("tenant-b"), ())
        self.assertEqual(store.count(), 1)
        self.assertNotIn("content", str(case.to_json()))

    def test_firestore_save_requires_the_current_fingerprint(self) -> None:
        client = FakeFirestoreClient()
        store = FirestoreCaseStore(client=client)
        first = make_case("case-b")
        store.save(first)
        second = MACHINE.transition(
            first,
            CaseState.DENIAL_PARSED,
            TIME,
            ACTOR,
            SOURCE,
            "case replay",
            (),
            "case-b:replay",
        )
        with self.assertRaises(CaseStoreConflict):
            store.save(second)
        store.save(second, expected_fingerprint=first.fingerprint())
        self.assertEqual(store.get("tenant-a", "case-b"), second)

    def test_atomic_workflow_persistence_keeps_case_and_session_at_one_version(self) -> None:
        client = FakeFirestoreClient()
        store = FirestoreCaseStore(client=client)
        sessions = FirestoreWorkflowSessionStore(client=client)
        persistence = FirestoreWorkflowPersistence(client=client)
        runtime = LocalCaseRuntime(
            AppealWorkflow(MACHINE),
            store=store,
            session_store=sessions,
            workflow_persistence=persistence,
        )

        waiting = runtime.start(demo_input(case_id="case-atomic", tenant_id="tenant-atomic"), at=TIME)
        session = sessions.get("tenant-atomic", "case-atomic")
        case = store.get("tenant-atomic", "case-atomic")
        assert session is not None
        assert case is not None
        self.assertEqual(session.case_fingerprint, case.fingerprint())
        self.assertEqual(waiting.workflow.case.fingerprint(), case.fingerprint())

        approved = runtime.approve(waiting, at=TIME)
        session_after = sessions.get("tenant-atomic", "case-atomic")
        case_after = store.get("tenant-atomic", "case-atomic")
        assert session_after is not None
        assert case_after is not None
        self.assertEqual(session_after.case_fingerprint, case_after.fingerprint())
        self.assertEqual(approved.workflow.case.fingerprint(), case_after.fingerprint())

    def test_firestore_fingerprint_tampering_fails_closed(self) -> None:
        client = FakeFirestoreClient()
        store = FirestoreCaseStore(client=client)
        case = make_case("case-c")
        store.save(case)
        document_path = ("appeal_tenants", "tenant-a", "cases", "case-c")
        tampered = dict(client.documents[document_path])
        tampered["fingerprint"] = "tampered"
        client.documents[document_path] = tampered
        with self.assertRaises(CaseStoreConflict):
            store.get("tenant-a", "case-c")

    def test_service_refreshes_a_cached_result_from_durable_state(self) -> None:
        client = FakeFirestoreClient()
        store = FirestoreCaseStore(client=client)
        sessions = FirestoreWorkflowSessionStore(client=client)
        persistence = FirestoreWorkflowPersistence(client=client)
        first_service = LocalAppealService(
            LocalCaseRuntime(
                AppealWorkflow(MACHINE),
                store=store,
                session_store=sessions,
                workflow_persistence=persistence,
            )
        )
        first_service.open_demo_case(at=TIME)
        submitted = first_service.approve("tenant-demo", "case-demo-001", at=TIME)
        self.assertEqual(submitted.to_public_json()["case_state"], "AWAITING_DETERMINATION")

        restarted = LocalAppealService(
            LocalCaseRuntime(
                AppealWorkflow(MACHINE),
                store=store,
                session_store=sessions,
                workflow_persistence=persistence,
            )
        )
        closed = restarted.adjudicate("tenant-demo", "case-demo-001", at=TIME)
        self.assertEqual(closed.to_public_json()["case_state"], "CLOSED_WON")
        refreshed = first_service.get("tenant-demo", "case-demo-001")
        self.assertEqual(refreshed.to_public_json()["case_state"], "CLOSED_WON")

    def test_service_reads_persisted_metadata_after_process_restart(self) -> None:
        client = FakeFirestoreClient()
        store = FirestoreCaseStore(client=client)
        sessions = FirestoreWorkflowSessionStore(client=client)
        first_service = LocalAppealService(
            LocalCaseRuntime(AppealWorkflow(MACHINE), store=store, session_store=sessions)
        )
        first_service.open_demo_case(at=TIME)

        restarted = LocalAppealService(
            LocalCaseRuntime(AppealWorkflow(MACHINE), store=store, session_store=sessions)
        )
        view = restarted.get("tenant-demo", "case-demo-001")
        self.assertEqual(view.to_public_json()["outcome"], "awaiting_clinician")
        self.assertEqual(len(restarted.board("tenant-demo")), 1)
        approved = restarted.approve("tenant-demo", "case-demo-001", at=TIME)
        self.assertEqual(approved.to_public_json()["outcome"], "submitted")

        resumed_again = LocalAppealService(
            LocalCaseRuntime(AppealWorkflow(MACHINE), store=store, session_store=sessions)
        )
        closed = resumed_again.adjudicate("tenant-demo", "case-demo-001", at=TIME)
        self.assertEqual(closed.to_public_json()["outcome"], "closed_won")
        self.assertNotIn("advanced imaging", str(client.documents))
        self.assertNotIn("conservative therapy completed", str(client.documents))


if __name__ == "__main__":
    unittest.main()
