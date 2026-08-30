"""Reference-only MCP tools with explicit Appeal capability enforcement.

The server intentionally keeps the Submission Gate out of ``tools/list``.
Read tools expose bounded synthetic references; the mutation tool is an
internal authorization seam and never performs an external side effect.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from collections.abc import Mapping
from typing import Final

from appeal_agents.permissions import AgentPolicyRegistry, CapabilityDenied

from .registry import AgentRegistry


class McpRequestRejected(ValueError):
    """Raised when an MCP request is malformed or outside its contract."""


def _require(value: str, label: str) -> str:
    if not value.strip():
        raise McpRequestRejected(f"{label} must not be empty")
    if len(value) > 160:
        raise McpRequestRejected(f"{label} is too long")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise McpRequestRejected(f"{label} must be a string")
    return _require(value, label)


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise McpRequestRejected(f"{label} must be a boolean")
    return value


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise McpRequestRejected("MCP timestamp must be timezone-aware")
    return current.astimezone(UTC)


@dataclass(frozen=True)
class McpToolDefinition:
    """A tool's public schema plus its local policy requirements."""

    name: str
    description: str
    capability: str
    read_scope: str | None
    write_scope: str | None
    patient_scoped: bool
    mutation: bool
    discoverable: bool
    input_schema: dict[str, object]

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {
                "title": self.name.removeprefix("appeal.").replace("_", " ").title(),
                "readOnlyHint": not self.mutation,
                "destructiveHint": self.mutation,
                "idempotentHint": not self.mutation,
                "openWorldHint": False,
            },
        }


def _schema(*, patient_id: bool = False, mutation: bool = False) -> dict[str, object]:
    properties: dict[str, object] = {
        "tenant_id": {"type": "string", "minLength": 1, "maxLength": 160},
        "case_id": {"type": "string", "minLength": 1, "maxLength": 160},
    }
    required = ["tenant_id", "case_id"]
    if patient_id:
        properties["patient_id"] = {"type": "string", "minLength": 1, "maxLength": 160}
        required.append("patient_id")
    if mutation:
        properties.update(
            {
                "clinician_approved": {"type": "boolean"},
                "vetoes_clear": {"type": "boolean"},
                "deadline_valid": {"type": "boolean"},
                "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 160},
            }
        )
        required.extend(
            ["clinician_approved", "vetoes_clear", "deadline_valid", "idempotency_key"]
        )
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


MCP_TOOL_DEFINITIONS: Final[tuple[McpToolDefinition, ...]] = (
    McpToolDefinition(
        name="appeal.read_denial_reference",
        description="Read bounded metadata for a quarantined or parsed synthetic denial reference.",
        capability="denial.read",
        read_scope="denial_reference",
        write_scope=None,
        patient_scoped=False,
        mutation=False,
        discoverable=True,
        input_schema=_schema(),
    ),
    McpToolDefinition(
        name="appeal.read_case_state",
        description="Read bounded synthetic case-state metadata and the next control-plane boundary.",
        capability="case.read",
        read_scope="case_state",
        write_scope=None,
        patient_scoped=False,
        mutation=False,
        discoverable=True,
        input_schema=_schema(),
    ),
    McpToolDefinition(
        name="appeal.read_case_metadata",
        description="Read tenant- and case-scoped metadata without clinical content.",
        capability="case.metadata.read",
        read_scope="case_metadata",
        write_scope=None,
        patient_scoped=False,
        mutation=False,
        discoverable=True,
        input_schema=_schema(),
    ),
    McpToolDefinition(
        name="appeal.read_scoped_evidence",
        description="Read only a patient-scoped synthetic evidence reference, never chart prose.",
        capability="clinical-chart.read",
        read_scope="scoped_fhir_chart",
        write_scope=None,
        patient_scoped=True,
        mutation=False,
        discoverable=True,
        input_schema=_schema(patient_id=True),
    ),
    McpToolDefinition(
        name="appeal.read_policy_clause",
        description="Read a versioned synthetic payer-policy clause reference.",
        capability="policy.read",
        read_scope="policy_corpus",
        write_scope=None,
        patient_scoped=False,
        mutation=False,
        discoverable=True,
        input_schema=_schema(),
    ),
    McpToolDefinition(
        name="appeal.read_payer_determination",
        description="Read bounded synthetic payer outcome metadata without payer credentials or raw content.",
        capability="payer.read",
        read_scope="case_memory",
        write_scope=None,
        patient_scoped=False,
        mutation=False,
        discoverable=True,
        input_schema=_schema(),
    ),
    McpToolDefinition(
        name="appeal.request_external_mutation",
        description="Internal Submission Gate authorization seam; never discoverable and never directly executes a mutation.",
        capability="external.mutation",
        read_scope=None,
        write_scope="external_mutation",
        patient_scoped=False,
        mutation=True,
        discoverable=False,
        input_schema=_schema(mutation=True),
    ),
)


@dataclass(frozen=True)
class McpAuditRecord:
    request_id: str
    recorded_at: datetime
    agent_role: str
    tenant_id: str
    case_id: str
    tool: str
    decision: str
    reason_code: str
    required_capability: str
    required_scope: str | None
    mutation: bool
    response_content_persisted: bool = False

    def to_json(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "recorded_at": self.recorded_at.isoformat().replace("+00:00", "Z"),
            "agent_role": self.agent_role,
            "tenant_id": self.tenant_id,
            "case_id": self.case_id,
            "tool": self.tool,
            "decision": self.decision,
            "reason_code": self.reason_code,
            "required_capability": self.required_capability,
            "required_scope": self.required_scope,
            "mutation": self.mutation,
            "response_content_persisted": self.response_content_persisted,
        }


class McpToolServer:
    """MCP tool catalog and policy gate for synthetic Appeal calls."""

    _CONTROL_ROLE: Final[str] = "submission_gate"

    def __init__(self, registry: AgentRegistry, policies: AgentPolicyRegistry) -> None:
        self.registry = registry
        self.policies = policies
        self._definitions = {definition.name: definition for definition in MCP_TOOL_DEFINITIONS}
        self._audit: list[McpAuditRecord] = []
        self._request_counter = 0
        if self._CONTROL_ROLE not in policies.roles():
            raise ValueError("the non-discoverable Submission Gate policy is required")

    def list_tools(self) -> tuple[dict[str, object], ...]:
        return tuple(
            definition.to_json()
            for definition in MCP_TOOL_DEFINITIONS
            if definition.discoverable
        )

    @property
    def audit_records(self) -> tuple[McpAuditRecord, ...]:
        return tuple(self._audit)

    def audit_json(self) -> list[dict[str, object]]:
        return [record.to_json() for record in self._audit]

    def call_tool(
        self,
        name: str,
        arguments: Mapping[str, object],
        *,
        request_id: str | None = None,
        at: datetime | None = None,
    ) -> dict[str, object]:
        definition = self._definitions.get(_require(name, "MCP tool name"))
        if definition is None:
            return {
                "decision": "DENIED",
                "tool": name,
                "reason_code": "unknown_tool",
                "isError": True,
            }
        if not isinstance(arguments, Mapping):
            raise McpRequestRejected("MCP tool arguments must be an object")
        role = _string(arguments.get("agent_role"), "agent role")
        tenant_id = _string(arguments.get("tenant_id"), "tenant ID")
        case_id = _string(arguments.get("case_id"), "case ID")
        request = self._request_id(request_id)
        recorded_at = _utc(at)

        if definition.mutation and definition.discoverable:
            return self._deny(
                definition,
                request,
                recorded_at,
                role,
                tenant_id,
                case_id,
                "mutation_tool_must_not_be_discoverable",
            )

        registration = None
        if role != self._CONTROL_ROLE:
            try:
                registration = self.registry.for_role(role)
            except KeyError:
                return self._deny(
                    definition,
                    request,
                    recorded_at,
                    role,
                    tenant_id,
                    case_id,
                    "principal_not_registered",
                )
            if definition.name not in registration.allowed_tools:
                if definition.capability not in registration.capabilities:
                    return self._deny(
                        definition,
                        request,
                        recorded_at,
                        role,
                        tenant_id,
                        case_id,
                        "capability_not_in_registered_scope",
                    )
                return self._deny(
                    definition,
                    request,
                    recorded_at,
                    role,
                    tenant_id,
                    case_id,
                    "tool_not_registered_for_agent",
                )
            if definition.capability not in registration.capabilities:
                return self._deny(
                    definition,
                    request,
                    recorded_at,
                    role,
                    tenant_id,
                    case_id,
                    "capability_not_in_registered_scope",
                )

        policy = self.policies.for_role(role)
        try:
            if definition.read_scope is not None:
                policy.require_read(definition.read_scope)
            if definition.write_scope is not None:
                policy.require_write(definition.write_scope)
                policy.require_external_mutation()
        except CapabilityDenied:
            return self._deny(
                definition,
                request,
                recorded_at,
                role,
                tenant_id,
                case_id,
                "policy_scope_denied",
            )

        if definition.patient_scoped:
            patient_id = _string(arguments.get("patient_id"), "patient ID")
            try:
                policy.require_patient_scope(patient_id, patient_id)
            except CapabilityDenied:
                return self._deny(
                    definition,
                    request,
                    recorded_at,
                    role,
                    tenant_id,
                    case_id,
                    "patient_scope_denied",
                )
        if definition.mutation:
            return self._mutation_result(
                definition,
                arguments,
                request,
                recorded_at,
                role,
                tenant_id,
                case_id,
            )
        result = self._read_result(definition, arguments, tenant_id, case_id)
        self._record(
            request,
            recorded_at,
            role,
            tenant_id,
            case_id,
            definition,
            "AUTHORIZED",
            "scope_allowed",
        )
        return result

    def _read_result(
        self,
        definition: McpToolDefinition,
        arguments: Mapping[str, object],
        tenant_id: str,
        case_id: str,
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "decision": "AUTHORIZED",
            "tool": definition.name,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "scope": definition.read_scope,
            "reference_only": True,
            "response_content_persisted": False,
        }
        if definition.name == "appeal.read_denial_reference":
            result["denial_reference_hash"] = _hash(f"{tenant_id}:{case_id}:denial")
        elif definition.name == "appeal.read_case_state":
            result["case_state"] = "synthetic_reference_only"
            result["next_boundary"] = "deterministic_control_plane"
        elif definition.name == "appeal.read_case_metadata":
            result["metadata_fields"] = ["tenant_id", "case_id", "state", "deadline_status"]
        elif definition.name == "appeal.read_scoped_evidence":
            patient_id = _string(arguments.get("patient_id"), "patient ID")
            result["patient_scope_hash"] = _hash(patient_id)
            result["references"] = [
                {
                    "resource_type": "Observation",
                    "resource_id": "synthetic-observation-001",
                    "reference_hash": _hash(f"{tenant_id}:{case_id}:{patient_id}:observation"),
                }
            ]
        elif definition.name == "appeal.read_policy_clause":
            result["policy_clause_reference"] = _hash(f"{tenant_id}:{case_id}:policy-clause")
            result["policy_version"] = "synthetic-policy-v1"
        elif definition.name == "appeal.read_payer_determination":
            result["payer_status"] = "synthetic_pending"
            result["evidence_ref_count"] = 0
        return result

    def _mutation_result(
        self,
        definition: McpToolDefinition,
        arguments: Mapping[str, object],
        request: str,
        recorded_at: datetime,
        role: str,
        tenant_id: str,
        case_id: str,
    ) -> dict[str, object]:
        checks = (
            ("clinician_approval_missing", _boolean(arguments.get("clinician_approved"), "clinician_approved")),
            ("veto_not_clear", _boolean(arguments.get("vetoes_clear"), "vetoes_clear")),
            ("deadline_invalid", _boolean(arguments.get("deadline_valid"), "deadline_valid")),
        )
        for reason_code, passed in checks:
            if not passed:
                return self._deny(
                    definition,
                    request,
                    recorded_at,
                    role,
                    tenant_id,
                    case_id,
                    reason_code,
                )
        idempotency_key = _string(arguments.get("idempotency_key"), "idempotency key")
        if not idempotency_key.startswith(f"{case_id}:"):
            return self._deny(
                definition,
                request,
                recorded_at,
                role,
                tenant_id,
                case_id,
                "idempotency_scope_invalid",
            )
        self._record(
            request,
            recorded_at,
            role,
            tenant_id,
            case_id,
            definition,
            "AUTHORIZED",
            "submission_gate_checks_clear",
        )
        return {
            "decision": "AUTHORIZED",
            "tool": definition.name,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "execution": "not_executed",
            "mutation_count": 0,
            "requires_external_executor": True,
            "idempotency_key_hash": _hash(idempotency_key),
            "reference_only": True,
            "response_content_persisted": False,
        }

    def _deny(
        self,
        definition: McpToolDefinition,
        request: str,
        recorded_at: datetime,
        role: str,
        tenant_id: str,
        case_id: str,
        reason_code: str,
    ) -> dict[str, object]:
        self._record(
            request,
            recorded_at,
            role,
            tenant_id,
            case_id,
            definition,
            "DENIED",
            reason_code,
        )
        return {
            "decision": "DENIED",
            "tool": definition.name,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "reason_code": reason_code,
            "required_capability": definition.capability,
            "required_scope": definition.read_scope or definition.write_scope,
            "mutation": definition.mutation,
            "isError": True,
            "response_content_persisted": False,
        }

    def _record(
        self,
        request: str,
        recorded_at: datetime,
        role: str,
        tenant_id: str,
        case_id: str,
        definition: McpToolDefinition,
        decision: str,
        reason_code: str,
    ) -> None:
        self._audit.append(
            McpAuditRecord(
                request_id=request,
                recorded_at=recorded_at,
                agent_role=role,
                tenant_id=tenant_id,
                case_id=case_id,
                tool=definition.name,
                decision=decision,
                reason_code=reason_code,
                required_capability=definition.capability,
                required_scope=definition.read_scope or definition.write_scope,
                mutation=definition.mutation,
            )
        )

    def _request_id(self, request_id: str | None) -> str:
        if request_id is not None:
            return _require(request_id, "MCP request ID")
        self._request_counter += 1
        return f"mcp-request-{self._request_counter:06d}"


class McpJsonRpcServer:
    """Small MCP JSON-RPC surface over the tool server."""

    def __init__(self, tools: McpToolServer) -> None:
        self.tools = tools

    def handle(
        self,
        request: Mapping[str, object],
        *,
        principal_role: str | None = None,
        at: datetime | None = None,
    ) -> dict[str, object]:
        request_id = request.get("id")
        response_id: object = request_id if isinstance(request_id, (str, int)) or request_id is None else None
        if request.get("jsonrpc") != "2.0":
            return self._error(response_id, -32600, "invalid_jsonrpc_request")
        method = request.get("method")
        if not isinstance(method, str):
            return self._error(response_id, -32600, "method_required")
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": response_id,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "appeal-mcp", "version": "0.1.0"},
                },
            }
        if method == "notifications/initialized":
            return {"jsonrpc": "2.0", "id": response_id, "result": {}}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": response_id, "result": {}}
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": response_id,
                "result": {"tools": list(self.tools.list_tools())},
            }
        if method == "tools/call":
            params = request.get("params")
            if not isinstance(params, Mapping):
                return self._error(response_id, -32602, "tool_call_params_required")
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, Mapping):
                return self._error(response_id, -32602, "tool_name_and_arguments_required")
            call_arguments = dict(arguments)
            if principal_role is not None:
                call_arguments["agent_role"] = principal_role
            elif "agent_role" not in call_arguments:
                return self._error(response_id, -32602, "authenticated_agent_principal_required")
            try:
                result = self.tools.call_tool(
                    name,
                    call_arguments,
                    request_id=self._request_id(response_id),
                    at=at,
                )
            except (McpRequestRejected, CapabilityDenied) as error:
                return self._error(response_id, -32602, str(error))
            is_error = result.get("decision") == "DENIED" or result.get("isError") is True
            return {
                "jsonrpc": "2.0",
                "id": response_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, sort_keys=True),
                        }
                    ],
                    "structuredContent": result,
                    "isError": is_error,
                },
            }
        return self._error(response_id, -32601, "method_not_found")

    @staticmethod
    def _request_id(value: object) -> str:
        if isinstance(value, bool) or value is None:
            return "rpc-notification"
        if isinstance(value, (str, int)):
            return f"rpc-{value}"
        return "rpc-invalid"

    @staticmethod
    def _error(response_id: object, code: int, message: str) -> dict[str, object]:
        return {
            "jsonrpc": "2.0",
            "id": response_id,
            "error": {"code": code, "message": message},
        }


__all__ = [
    "MCP_TOOL_DEFINITIONS",
    "McpAuditRecord",
    "McpJsonRpcServer",
    "McpRequestRejected",
    "McpToolDefinition",
    "McpToolServer",
]
