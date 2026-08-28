"""A small local case-board service over the Appeal runtime."""

from __future__ import annotations

from datetime import UTC, datetime

from appeal_agents import AppealInput, AppealWorkflow
from appeal_agents.demo import demo_input
from appeal_core import CaseStateMachine, DeadlineCatalog
from appeal_platform import LocalCaseRuntime, PayerAdjudicator, RuntimeResult


class CaseNotFound(KeyError):
    """Raised when a tenant-scoped case is not held by the local service."""


def _now(value: datetime | None) -> datetime:
    return (value or datetime.now(UTC)).astimezone(UTC)


class LocalAppealService:
    """Case-board operations with an explicit human approval boundary."""

    def __init__(self, runtime: LocalCaseRuntime) -> None:
        self.runtime = runtime
        self._results: dict[tuple[str, str], RuntimeResult] = {}

    @classmethod
    def for_repository(cls, root: str) -> "LocalAppealService":
        from pathlib import Path

        deadlines = DeadlineCatalog.from_path(Path(root) / "config" / "deadlines.yaml")
        return cls(LocalCaseRuntime(AppealWorkflow(CaseStateMachine(deadlines))))

    def open_case(self, appeal_input: AppealInput, *, at: datetime | None = None) -> RuntimeResult:
        key = (appeal_input.tenant_id, appeal_input.case_id)
        if key in self._results:
            raise ValueError("case is already open in the local service")
        result = self.runtime.start(appeal_input, at=_now(at))
        self._results[key] = result
        return result

    def open_demo_case(self, *, at: datetime | None = None) -> RuntimeResult:
        return self.open_case(demo_input(), at=at)

    def approve(self, tenant_id: str, case_id: str, *, at: datetime | None = None) -> RuntimeResult:
        current = self._require(tenant_id, case_id)
        result = self.runtime.approve(current, at=_now(at))
        self._results[(tenant_id, case_id)] = result
        return result

    def adjudicate(self, tenant_id: str, case_id: str, *, at: datetime | None = None) -> RuntimeResult:
        current = self._require(tenant_id, case_id)
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

    def get(self, tenant_id: str, case_id: str) -> RuntimeResult:
        return self._require(tenant_id, case_id)

    def board(self, tenant_id: str) -> tuple[dict[str, object], ...]:
        tenant_id = tenant_id.strip()
        if not tenant_id:
            raise ValueError("tenant ID must not be empty")
        return tuple(
            result.to_public_json()
            for (scope, _), result in sorted(self._results.items())
            if scope == tenant_id
        )

    def _require(self, tenant_id: str, case_id: str) -> RuntimeResult:
        result = self._results.get((tenant_id, case_id))
        if result is None:
            raise CaseNotFound(f"case {case_id!r} was not found for tenant {tenant_id!r}")
        return result
