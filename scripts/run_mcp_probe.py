"""Run the aggregate-only MCP authorization probe for Appeal."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from appeal_agents import default_policy_registry
from appeal_platform import AgentRegistry, McpJsonRpcServer, McpToolServer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "evidence" / "mcp-governance-probe.json"
DEFAULT_REGISTRY = ROOT / "config" / "agent_registry.json"


def _structured(response: dict[str, object]) -> dict[str, object]:
    result = response.get("result")
    if not isinstance(result, dict):
        raise ValueError("MCP response is missing result")
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        raise ValueError("MCP response is missing structuredContent")
    return cast(dict[str, object], structured)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    recorded_at = datetime.now(UTC)
    registry = AgentRegistry.from_path(args.registry)
    tools = McpToolServer(registry, default_policy_registry())
    rpc = McpJsonRpcServer(tools)
    tenant_id = "tenant-demo-mcp"

    initialize = rpc.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    listed = rpc.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    authorized_read = _structured(
        rpc.handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "appeal.read_scoped_evidence",
                    "arguments": {
                        "tenant_id": tenant_id,
                        "case_id": "case-demo-mcp-authorized-read",
                        "patient_id": "synthetic-patient-001",
                    },
                },
            },
            principal_role="evidence_miner",
            at=recorded_at,
        )
    )
    denied_chart_read = _structured(
        rpc.handle(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "appeal.read_scoped_evidence",
                    "arguments": {
                        "tenant_id": tenant_id,
                        "case_id": "case-demo-mcp-denied-chart",
                        "patient_id": "synthetic-patient-001",
                    },
                },
            },
            principal_role="policy_analyst",
            at=recorded_at,
        )
    )
    denied_mutation = _structured(
        rpc.handle(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "appeal.request_external_mutation",
                    "arguments": {
                        "tenant_id": tenant_id,
                        "case_id": "case-demo-mcp-denied-mutation",
                        "clinician_approved": True,
                        "vetoes_clear": True,
                        "deadline_valid": True,
                        "idempotency_key": "case-demo-mcp-denied-mutation:level-1",
                    },
                },
            },
            principal_role="policy_analyst",
            at=recorded_at,
        )
    )
    gate_authorization = _structured(
        rpc.handle(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "appeal.request_external_mutation",
                    "arguments": {
                        "tenant_id": tenant_id,
                        "case_id": "case-demo-mcp-gate-check",
                        "clinician_approved": True,
                        "vetoes_clear": True,
                        "deadline_valid": True,
                        "idempotency_key": "case-demo-mcp-gate-check:level-1",
                    },
                },
            },
            principal_role="submission_gate",
            at=recorded_at,
        )
    )

    listed_result = listed.get("result")
    if not isinstance(listed_result, dict):
        raise ValueError("tools/list response is invalid")
    listed_tools = listed_result.get("tools")
    if not isinstance(listed_tools, list):
        raise ValueError("tools/list did not return a list")
    listed_names = [
        str(tool.get("name"))
        for tool in listed_tools
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    ]
    checks = {
        "initialize_ok": isinstance(initialize.get("result"), dict),
        "seven_registry_agents": len(registry.roles()) == 7,
        "six_discoverable_read_tools": len(listed_names) == 6,
        "mutation_tool_hidden": "appeal.request_external_mutation" not in listed_names,
        "scoped_read_authorized": authorized_read.get("decision") == "AUTHORIZED",
        "chart_read_denied": (
            denied_chart_read.get("decision") == "DENIED"
            and denied_chart_read.get("reason_code") == "capability_not_in_registered_scope"
        ),
        "mutation_denied_for_policy_analyst": (
            denied_mutation.get("decision") == "DENIED"
            and denied_mutation.get("reason_code") == "capability_not_in_registered_scope"
        ),
        "gate_authorized_without_execution": (
            gate_authorization.get("decision") == "AUTHORIZED"
            and gate_authorization.get("execution") == "not_executed"
            and gate_authorization.get("mutation_count") == 0
        ),
    }
    report: dict[str, object] = {
        "schema_version": "0.1",
        "recorded_at": recorded_at.isoformat().replace("+00:00", "Z"),
        "protocol": "mcp-json-rpc",
        "registry_path": str(args.registry),
        "registry_roles": list(registry.roles()),
        "synthetic_only": True,
        "response_content_persisted": False,
        "mutation_executed": False,
        "checks": checks,
        "status": "verified" if all(checks.values()) else "failed",
        "authorized_read": authorized_read,
        "denied_chart_read": denied_chart_read,
        "denied_mutation": denied_mutation,
        "gate_authorization": gate_authorization,
        "audit_records": tools.audit_json(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
