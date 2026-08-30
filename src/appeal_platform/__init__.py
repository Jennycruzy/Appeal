"""Local platform boundaries for the Appeal workflow.

These adapters keep the local path runnable while exposing the managed seams
for Pub/Sub, Firestore, Memory Bank, and a separately deployed payer service.
The Firestore case-metadata adapter is used by the Cloud Run deployment; the
remaining managed boundaries are explicit adapters with synthetic-only gates.
"""

from .agent_runtime import (
    AgentRuntimeInvocation,
    AgentRuntimeInvocationInProgress,
    AgentRuntimeSubscriber,
    FirestoreAgentRuntimeInvocationStore,
    InvocationClaim,
    LocalAgentRuntimeInvocationStore,
    ManagedAgentRuntimeInvoker,
)

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
from .mcp import (
    MCP_TOOL_DEFINITIONS,
    McpAuditRecord,
    McpJsonRpcServer,
    McpRequestRejected,
    McpToolDefinition,
    McpToolServer,
)
from .payer import PayerAdjudicator, PayerDecision, PayerDecisionStatus
from .pubsub import FirestorePubSubEventSpine
from .receipts import FirestoreReceiptLedger
from .runtime import LocalCaseRuntime, RuntimeResult, SentinelTickResult
from .sessions import (
    FirestoreWorkflowSessionStore,
    LocalWorkflowSessionStore,
    WorkflowSession,
    WorkflowSessionConflict,
)
from .store import CaseStore, CaseStoreConflict, CaseStoreScopeError, FirestoreCaseStore
from .registry import AgentRegistration, AgentRegistry, default_agent_registry
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
    "AgentRegistration",
    "AgentRegistry",
    "default_agent_registry",
    "FirestoreAgentRuntimeInvocationStore",
    "FirestoreReceiptLedger",
    "FirestorePubSubEventSpine",
    "FirestoreWorkflowSessionStore",
    "ActionStatus",
    "DeliveryReceipt",
    "DomainEvent",
    "EventIdempotencyConflict",
    "AgentRuntimeInvocation",
    "AgentRuntimeInvocationInProgress",
    "AgentRuntimeSubscriber",
    "InvocationClaim",
    "LocalCaseRuntime",
    "LocalAgentRuntimeInvocationStore",
    "LocalEventSpine",
    "LocalWorkflowSessionStore",
    "MemoryRecord",
    "MemoryScopeError",
    "MemoryWriteBlocked",
    "MCP_TOOL_DEFINITIONS",
    "McpAuditRecord",
    "McpJsonRpcServer",
    "McpRequestRejected",
    "McpToolDefinition",
    "McpToolServer",
    "ManagedAgentRuntimeInvoker",
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
