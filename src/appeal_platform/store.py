"""Tenant-scoped local case storage with optimistic concurrency checks."""

from __future__ import annotations

from appeal_core import Case


class CaseStoreScopeError(ValueError):
    """Raised when a case is accessed outside its tenant scope."""


class CaseStoreConflict(ValueError):
    """Raised when a write would silently overwrite another case version."""


def _require(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


class CaseStore:
    """An in-process stand-in for a tenant-partitioned Firestore collection."""

    def __init__(self) -> None:
        self._cases: dict[tuple[str, str], Case] = {}

    def save(self, case: Case, *, expected_fingerprint: str | None = None) -> Case:
        key = (case.tenant_id, case.case_id)
        existing = self._cases.get(key)
        if existing is None:
            if expected_fingerprint is not None:
                raise CaseStoreConflict("cannot compare an expected version for a new case")
            self._cases[key] = case
            return case
        if existing.fingerprint() == case.fingerprint():
            return existing
        if expected_fingerprint is None or existing.fingerprint() != expected_fingerprint:
            raise CaseStoreConflict("case version changed or expected_fingerprint was omitted")
        self._cases[key] = case
        return case

    def get(self, tenant_id: str, case_id: str) -> Case | None:
        tenant_id = _require(tenant_id, "tenant ID")
        case_id = _require(case_id, "case ID")
        case = self._cases.get((tenant_id, case_id))
        if case is not None and case.tenant_id != tenant_id:
            raise CaseStoreScopeError("case belongs to another tenant")
        return case

    def require(self, tenant_id: str, case_id: str) -> Case:
        case = self.get(tenant_id, case_id)
        if case is None:
            raise KeyError(f"case {case_id!r} was not found in tenant {tenant_id!r}")
        return case

    def list_tenant(self, tenant_id: str) -> tuple[Case, ...]:
        tenant_id = _require(tenant_id, "tenant ID")
        return tuple(case for (scope, _), case in self._cases.items() if scope == tenant_id)

    def count(self) -> int:
        return len(self._cases)
