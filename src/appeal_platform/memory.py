"""Case- and tenant-scoped local memory with a security inspection boundary."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from appeal_core import EvidenceRef

from appeal_agents.security import InspectionResult, InspectionStatus, LocalSecurityBoundary


class MemoryScopeError(ValueError):
    """Raised when a caller attempts to cross a memory scope."""


class MemoryWriteBlocked(ValueError):
    """Raised when the memory security boundary blocks a write."""

    def __init__(self, inspection: InspectionResult) -> None:
        super().__init__(inspection.reason)
        self.inspection = inspection


def _require(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    tenant_id: str
    case_id: str
    agent: str
    kind: str
    content: str
    content_sha256: str
    created_at: datetime
    evidence_refs: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        for value, label in [
            (self.memory_id, "memory ID"),
            (self.tenant_id, "memory tenant ID"),
            (self.case_id, "memory case ID"),
            (self.agent, "memory agent"),
            (self.kind, "memory kind"),
            (self.content, "memory content"),
        ]:
            _require(value, label)
        _utc(self.created_at, "memory created_at")
        actual = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if self.content_sha256 != actual:
            raise ValueError("memory content_sha256 does not match content")

    def to_public_json(self) -> dict[str, object]:
        return {
            "memory_id": self.memory_id,
            "tenant_id": self.tenant_id,
            "case_id": self.case_id,
            "agent": self.agent,
            "kind": self.kind,
            "content_sha256": self.content_sha256,
            "created_at": self.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "evidence_ref_count": len(self.evidence_refs),
        }


class ScopedMemoryBank:
    """Memory with an exact `(tenant_id, case_id)` access condition."""

    def __init__(self, security: LocalSecurityBoundary | None = None) -> None:
        self.security = security or LocalSecurityBoundary()
        self._records: dict[tuple[str, str], list[MemoryRecord]] = {}
        self._by_id: dict[str, MemoryRecord] = {}

    def write(
        self,
        tenant_id: str,
        case_id: str,
        agent: str,
        kind: str,
        content: str,
        created_at: datetime,
        evidence_refs: tuple[EvidenceRef, ...] = (),
    ) -> MemoryRecord:
        tenant_id = _require(tenant_id, "memory tenant ID")
        case_id = _require(case_id, "memory case ID")
        agent = _require(agent, "memory agent")
        kind = _require(kind, "memory kind")
        content = _require(content, "memory content")
        inspection = self.security.inspect_memory(content)
        if inspection.status is InspectionStatus.BLOCKED:
            raise MemoryWriteBlocked(inspection)
        content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        memory_id = hashlib.sha256(
            f"{tenant_id}:{case_id}:{kind}:{content_sha256}".encode("utf-8")
        ).hexdigest()
        record = MemoryRecord(
            memory_id,
            tenant_id,
            case_id,
            agent,
            kind,
            content,
            content_sha256,
            _utc(created_at, "memory created_at"),
            evidence_refs,
        )
        existing = self._by_id.get(memory_id)
        if existing is not None:
            if existing != record:
                raise MemoryScopeError("memory id was reused with different content")
            return existing
        self._by_id[memory_id] = record
        self._records.setdefault((tenant_id, case_id), []).append(record)
        return record

    def read(self, tenant_id: str, case_id: str) -> tuple[MemoryRecord, ...]:
        tenant_id = _require(tenant_id, "memory tenant ID")
        case_id = _require(case_id, "memory case ID")
        return tuple(self._records.get((tenant_id, case_id), ()))

    def read_for(self, requester_tenant_id: str, requester_case_id: str, target_case_id: str) -> tuple[MemoryRecord, ...]:
        requester_tenant_id = _require(requester_tenant_id, "requester tenant ID")
        requester_case_id = _require(requester_case_id, "requester case ID")
        target_case_id = _require(target_case_id, "target case ID")
        if requester_case_id != target_case_id:
            raise MemoryScopeError("memory access condition requires the open case ID")
        return self.read(requester_tenant_id, target_case_id)

    def public_records(self) -> tuple[dict[str, object], ...]:
        return tuple(record.to_public_json() for record in self._by_id.values())
