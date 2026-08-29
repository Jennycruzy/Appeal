"""Local platform boundaries for the Appeal workflow.

These adapters keep the local path runnable while exposing the managed seams
for Pub/Sub, Firestore, Memory Bank, and a separately deployed payer service.
The Firestore case-metadata adapter is used by the Cloud Run deployment; the
remaining managed boundaries are still explicit future targets.
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
from .runtime import LocalCaseRuntime, RuntimeResult, SentinelTickResult
from .sessions import (
    FirestoreWorkflowSessionStore,
    LocalWorkflowSessionStore,
    WorkflowSession,
    WorkflowSessionConflict,
)
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
    "FirestoreWorkflowSessionStore",
    "ActionStatus",
    "DeliveryReceipt",
    "DomainEvent",
    "EventIdempotencyConflict",
    "LocalCaseRuntime",
    "LocalEventSpine",
    "LocalWorkflowSessionStore",
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
    "SentinelTickResult",
    "ScopedMemoryBank",
    "WorkflowSession",
    "WorkflowSessionConflict",
]
