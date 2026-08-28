"""Local platform boundaries for the Appeal workflow.

These adapters model the seams that will later be backed by Pub/Sub,
Firestore, Memory Bank, and a separately deployed payer service. They keep
the local path runnable without claiming that a cloud deployment exists.
"""

from .events import (
    DomainEvent,
    EventIdempotencyConflict,
    LocalEventSpine,
    DeliveryReceipt,
)
from .memory import (
    MemoryRecord,
    MemoryScopeError,
    MemoryWriteBlocked,
    ScopedMemoryBank,
)
from .payer import PayerAdjudicator, PayerDecision, PayerDecisionStatus
from .runtime import LocalCaseRuntime, RuntimeResult
from .store import CaseStore, CaseStoreConflict, CaseStoreScopeError, FirestoreCaseStore
from .reversibility import (
    ActionStatus,
    ReversibleAction,
    ReversibilityConflict,
    ReversibilityEntry,
    ReversibilityLedger,
    ReversibilityVerification,
)

__all__ = [
    "CaseStore",
    "CaseStoreConflict",
    "CaseStoreScopeError",
    "FirestoreCaseStore",
    "ActionStatus",
    "DeliveryReceipt",
    "DomainEvent",
    "EventIdempotencyConflict",
    "LocalCaseRuntime",
    "LocalEventSpine",
    "MemoryRecord",
    "MemoryScopeError",
    "MemoryWriteBlocked",
    "PayerAdjudicator",
    "PayerDecision",
    "PayerDecisionStatus",
    "ReversibleAction",
    "ReversibilityConflict",
    "ReversibilityEntry",
    "ReversibilityLedger",
    "ReversibilityVerification",
    "RuntimeResult",
    "ScopedMemoryBank",
]
