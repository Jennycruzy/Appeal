from __future__ import annotations

import unittest
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from appeal_core import Actor, ActorKind, Case, CaseState, CaseStateMachine, DecisionSource, DeadlineCatalog
from appeal_agents import AppealWorkflow
from appeal_platform import CaseStoreConflict, FirestoreCaseStore, LocalCaseRuntime
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


ROOT = Path(__file__).resolve().parents[1]
MACHINE = CaseStateMachine(DeadlineCatalog.from_path(ROOT / "config" / "deadlines.yaml"))
TIME = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
SOURCE = DecisionSource("deterministic", "test", "1")
ACTOR = Actor("test-agent", ActorKind.AGENT)


def make_case(case_id: str) -> Case:
    return MACHINE.create(case_id, "tenant-a", TIME, ACTOR, SOURCE)


class FirestoreStoreTests(unittest.TestCase):
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

    def test_service_reads_persisted_metadata_after_process_restart(self) -> None:
        client = FakeFirestoreClient()
        store = FirestoreCaseStore(client=client)
        first_service = LocalAppealService(LocalCaseRuntime(AppealWorkflow(MACHINE), store=store))
        first_service.open_demo_case(at=TIME)

        restarted = LocalAppealService(LocalCaseRuntime(AppealWorkflow(MACHINE), store=store))
        view = restarted.get("tenant-demo", "case-demo-001")
        self.assertEqual(view.to_public_json()["outcome"], "persisted_metadata")
        self.assertEqual(len(restarted.board("tenant-demo")), 1)
        with self.assertRaises(ValueError):
            restarted.approve("tenant-demo", "case-demo-001", at=TIME)


if __name__ == "__main__":
    unittest.main()
