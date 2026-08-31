from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from appeal_platform import (
    AgentRuntimeQueryError,
    AgentRuntimeInvocation,
    AgentRuntimeSubscriber,
    InvocationClaim,
    LocalAgentRuntimeInvocationStore,
    ManagedAgentRuntimeInvoker,
)
from appeal_platform.events import DomainEvent


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def trigger_event(*, tenant_id: str = "tenant-demo-secret", case_id: str = "case-demo-secret") -> DomainEvent:
    return DomainEvent.create(
        tenant_id,
        case_id,
        "appeal.workflow.event",
        f"{case_id}:workflow-event:intake-clear",
        NOW,
        {"agent": "intake", "status": "clear", "evidence_ref_count": 0},
    )


class FakeRemoteAgent:
    def __init__(self) -> None:
        self.requests: list[dict[str, str]] = []

    def async_stream_query(self, *, user_id: str, message: str):  # type: ignore[no-untyped-def]
        self.requests.append({"user_id": user_id, "message": message})

        async def stream():  # type: ignore[no-untyped-def]
            yield {"author": "intake", "text": "response content is not retained"}
            yield {"author": "policy_analyst", "text": "another response"}

        return stream()


class ErrorRemoteAgent:
    def async_stream_query(self, *, user_id: str, message: str):  # type: ignore[no-untyped-def]
        del user_id, message

        async def stream():  # type: ignore[no-untyped-def]
            yield {"author": "appeal_agent_fleet"}
            yield {"error_code": "_ResourceExhaustedError"}

        return stream()


class RecordingInvoker:
    def __init__(self, *, fail_once: bool = False) -> None:
        self.calls: list[DomainEvent] = []
        self.fail_once = fail_once

    def invoke(self, event: DomainEvent) -> AgentRuntimeInvocation:
        self.calls.append(event)
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("synthetic provider failure")
        return AgentRuntimeInvocation(
            event_id=event.event_id,
            status="completed",
            query_event_count=2,
            query_authors=("intake", "policy_analyst"),
            completed_at=NOW,
        )


class AgentRuntimeTests(unittest.TestCase):
    def test_managed_invoker_keeps_case_content_and_identifiers_out_of_request(self) -> None:
        remote = FakeRemoteAgent()
        invoker = ManagedAgentRuntimeInvoker(
            resource_name="projects/p/locations/r/reasoningEngines/1",
            project="p",
            location="r",
            agent=remote,
        )

        result = invoker.invoke(trigger_event())

        self.assertEqual(result.to_public_json()["status"], "completed")
        self.assertEqual(result.query_event_count, 2)
        self.assertEqual(result.query_authors, ("intake", "policy_analyst"))
        request = remote.requests[0]
        self.assertNotIn("tenant-demo-secret", request["message"])
        self.assertNotIn("case-demo-secret", request["message"])
        self.assertNotIn("tenant-demo-secret", request["user_id"])
        self.assertNotIn("case-demo-secret", request["user_id"])

    def test_error_event_is_not_reported_as_completed(self) -> None:
        invoker = ManagedAgentRuntimeInvoker(
            resource_name="projects/p/locations/r/reasoningEngines/1",
            project="p",
            location="r",
            agent=ErrorRemoteAgent(),
        )

        with self.assertRaisesRegex(AgentRuntimeQueryError, "ResourceExhausted"):
            invoker.invoke(trigger_event())

    def test_subscriber_allowlist_and_duplicate_delivery(self) -> None:
        invoker = RecordingInvoker()
        subscriber = AgentRuntimeSubscriber(invoker, LocalAgentRuntimeInvocationStore())

        first = subscriber.handle(trigger_event(), at=NOW)
        duplicate = subscriber.handle(trigger_event(), at=NOW + timedelta(seconds=1))
        skipped = subscriber.handle(
            DomainEvent.create(
                "tenant-demo-secret",
                "case-demo-secret-2",
                "appeal.workflow.event",
                "case-demo-secret-2:workflow-event:intake-blocked",
                NOW,
                {"agent": "intake", "status": "blocked", "evidence_ref_count": 0},
            ),
            at=NOW,
        )

        self.assertEqual(first["status"], "completed")
        self.assertEqual(duplicate["status"], "duplicate")
        self.assertEqual(skipped["status"], "skipped")
        self.assertEqual(len(invoker.calls), 1)

    def test_failed_invocation_is_retryable(self) -> None:
        invoker = RecordingInvoker(fail_once=True)
        subscriber = AgentRuntimeSubscriber(invoker, LocalAgentRuntimeInvocationStore())
        event = trigger_event()

        with self.assertRaises(RuntimeError):
            subscriber.handle(event, at=NOW)
        result = subscriber.handle(event, at=NOW + timedelta(seconds=1))

        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(invoker.calls), 2)

    def test_firestore_claim_state_is_durable_and_lease_based(self) -> None:
        from appeal_platform import FirestoreAgentRuntimeInvocationStore
        from test_firestore_store import FakeFirestoreClient

        event = trigger_event()
        store = FirestoreAgentRuntimeInvocationStore(
            client=FakeFirestoreClient(),
            claim_lease_seconds=60,
        )

        self.assertEqual(store.claim(event, at=NOW), InvocationClaim.CLAIMED)
        self.assertEqual(
            store.claim(event, at=NOW + timedelta(seconds=1)),
            InvocationClaim.IN_PROGRESS,
        )
        store.complete(
            event,
            AgentRuntimeInvocation(event.event_id, "completed", 1, ("intake",)),
            at=NOW + timedelta(seconds=2),
        )
        self.assertEqual(
            store.claim(event, at=NOW + timedelta(seconds=3)),
            InvocationClaim.COMPLETED,
        )


if __name__ == "__main__":
    unittest.main()
