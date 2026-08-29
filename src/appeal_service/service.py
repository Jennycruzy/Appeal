"""A small local case-board service over the Appeal runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import dataclass
from collections.abc import Mapping

from appeal_agents import AppealInput, AppealWorkflow
from appeal_agents.demo import demo_input
from appeal_core import Case, CaseState, CaseStateMachine, DeadlineCatalog
from appeal_platform import (
    AgentRuntimeSubscriber,
    DomainEvent,
    LocalCaseRuntime,
    PayerAdjudicator,
    RuntimeResult,
    SentinelTickResult,
)


class CaseNotFound(KeyError):
    """Raised when a tenant-scoped case is not held by the local service."""


def _now(value: datetime | None) -> datetime:
    return (value or datetime.now(UTC)).astimezone(UTC)


@dataclass(frozen=True)
class PersistedCaseView:
    """Public metadata shown when no resumable workflow capsule exists."""

    case: Case
    graph: dict[str, object]
    clock: Mapping[str, object]

    def to_public_json(self) -> dict[str, object]:
        return {
            "schema_version": "0.1",
            "agent_graph": self.graph,
            "outcome": "persisted_metadata",
            "case_state": self.case.state.value,
            "case": self.case.to_json(),
            "clock": self.clock,
            "events": [],
            "draft": None,
            "combinator": None,
            "failure_reason": "workflow_context_not_persisted",
            "external_mutation_count": sum(
                transition.to_state is CaseState.SUBMITTED_LEVEL_1
                for transition in self.case.transitions
            ),
        }


class LocalAppealService:
    """Case-board operations with an explicit human approval boundary."""

    def __init__(
        self,
        runtime: LocalCaseRuntime,
        *,
        agent_runtime_subscriber: AgentRuntimeSubscriber | None = None,
    ) -> None:
        self.runtime = runtime
        self.agent_runtime_subscriber = agent_runtime_subscriber
        self._results: dict[tuple[str, str], RuntimeResult] = {}

    @classmethod
    def for_repository(cls, root: str) -> "LocalAppealService":
        from pathlib import Path

        deadlines = DeadlineCatalog.from_path(Path(root) / "config" / "deadlines.yaml")
        return cls(LocalCaseRuntime(AppealWorkflow(CaseStateMachine(deadlines))))

    def open_case(self, appeal_input: AppealInput, *, at: datetime | None = None) -> RuntimeResult:
        key = (appeal_input.tenant_id, appeal_input.case_id)
        if key in self._results or self.runtime.store.get(*key) is not None:
            raise ValueError("case is already persisted for this tenant")
        result = self.runtime.start(appeal_input, at=_now(at))
        self._results[key] = result
        return result

    def open_demo_case(
        self,
        *,
        at: datetime | None = None,
        case_id: str = "case-demo-001",
        tenant_id: str = "tenant-demo",
        injection: bool = False,
        missing_evidence: bool = False,
    ) -> RuntimeResult:
        return self.open_case(
            demo_input(
                case_id=case_id,
                tenant_id=tenant_id,
                injection=injection,
                missing_evidence=missing_evidence,
            ),
            at=at,
        )

    def approve(self, tenant_id: str, case_id: str, *, at: datetime | None = None) -> RuntimeResult:
        current = self._require_live(tenant_id, case_id)
        result = self.runtime.approve(current, at=_now(at))
        self._results[(tenant_id, case_id)] = result
        return result

    def adjudicate(self, tenant_id: str, case_id: str, *, at: datetime | None = None) -> RuntimeResult:
        current = self._require_live(tenant_id, case_id)
        context = current.workflow.context
        if context is None or context.input.policy is None:
            raise ValueError("payer adjudication requires a versioned policy criterion")
        result = self.runtime.adjudicate(
            current,
            PayerAdjudicator(context.input.policy),
            at=_now(at),
        )
        self._results[(tenant_id, case_id)] = result
        return result

    def sentinel_tick(self, *, at: datetime | None = None) -> SentinelTickResult:
        report = self.runtime.sentinel_tick(at=_now(at))
        for key in report.updated_cases:
            self._results.pop(key, None)
        return report

    def accept_event(self, event: DomainEvent) -> dict[str, object]:
        """Accept a validated Pub/Sub event without granting it mutation rights."""

        self.runtime.spine.accept(event)
        result: dict[str, object] = {
            "status": "accepted",
            "event_id": event.event_id,
            "tenant_id": event.tenant_id,
            "case_id": event.case_id,
            "topic": event.topic,
        }
        if self.agent_runtime_subscriber is not None:
            result["agent_runtime"] = self.agent_runtime_subscriber.handle(event)
        return result

    def get(self, tenant_id: str, case_id: str) -> RuntimeResult | PersistedCaseView:
        current = self._results.get((tenant_id, case_id))
        if current is not None:
            return current
        resumed = self.runtime.resume(tenant_id, case_id)
        if resumed is not None:
            self._results[(tenant_id, case_id)] = resumed
            return resumed
        case = self.runtime.store.get(tenant_id, case_id)
        if case is None:
            raise CaseNotFound(f"case {case_id!r} was not found for tenant {tenant_id!r}")
        return self._persisted_view(case)

    def board(self, tenant_id: str) -> tuple[dict[str, object], ...]:
        tenant_id = tenant_id.strip()
        if not tenant_id:
            raise ValueError("tenant ID must not be empty")
        live = {
            key: result
            for key, result in self._results.items()
            if key[0] == tenant_id
        }
        views: list[dict[str, object]] = [result.to_public_json() for result in live.values()]
        for case in self.runtime.store.list_tenant(tenant_id):
            if (tenant_id, case.case_id) not in live:
                resumed = self.runtime.resume(tenant_id, case.case_id)
                if resumed is not None:
                    self._results[(tenant_id, case.case_id)] = resumed
                    views.append(resumed.to_public_json())
                else:
                    views.append(self._persisted_view(case).to_public_json())
        return tuple(views)

    def _require_live(self, tenant_id: str, case_id: str) -> RuntimeResult:
        result = self._results.get((tenant_id, case_id))
        if result is None:
            result = self.runtime.resume(tenant_id, case_id)
            if result is not None:
                self._results[(tenant_id, case_id)] = result
                return result
            if self.runtime.store.get(tenant_id, case_id) is not None:
                raise ValueError("workflow context is not available for this persisted case")
            raise CaseNotFound(f"case {case_id!r} was not found for tenant {tenant_id!r}")
        return result

    def _persisted_view(self, case: Case) -> PersistedCaseView:
        return PersistedCaseView(
            case=case,
            graph=self.runtime.workflow.graph.to_json(),
            clock=self.runtime.workflow.machine.statutory_clock(case).to_json(),
        )
