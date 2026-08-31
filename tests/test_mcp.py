from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from pathlib import Path

from appeal_platform import AgentRegistry, McpJsonRpcServer, McpToolServer
from appeal_service import McpHttpApi
from appeal_agents import default_policy_registry


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 29, 15, 0, tzinfo=UTC)


def mcp_server() -> McpToolServer:
    return McpToolServer(
        AgentRegistry.from_path(ROOT / "config" / "agent_registry.json"),
        default_policy_registry(),
    )


class McpGovernanceTests(unittest.TestCase):
    def test_registry_has_seven_discoverable_agents_and_no_submission_gate(self) -> None:
        registry = AgentRegistry.from_path(ROOT / "config" / "agent_registry.json")

        self.assertEqual(
            registry.roles(),
            (
                "intake",
                "denial_parser",
                "policy_analyst",
                "evidence_miner",
                "argument_builder",
                "deadline_sentinel",
                "escalation_strategist",
            ),
        )
        self.assertNotIn("submission_gate", registry.roles())

    def test_tools_list_hides_submission_gate_mutation(self) -> None:
        server = mcp_server()
        names = {str(tool["name"]) for tool in server.list_tools()}

        self.assertIn("appeal.read_scoped_evidence", names)
        self.assertIn("appeal.probe_denied_mutation", names)
        self.assertNotIn("appeal.request_external_mutation", names)

    def test_gateway_mutation_canary_is_discoverable_but_never_executes(self) -> None:
        server = mcp_server()

        result = server.call_tool(
            "appeal.probe_denied_mutation",
            {
                "agent_role": "evidence_miner",
                "tenant_id": "tenant-demo-mcp",
                "case_id": "case-demo-mcp-canary",
            },
            request_id="canary-001",
            at=NOW,
        )

        self.assertEqual(result["decision"], "DENIED")
        self.assertEqual(result["reason_code"], "governance_canary_never_executes")
        self.assertEqual(result["mutation"], True)
        self.assertEqual(server.audit_records[0].mutation, True)

    def test_evidence_miner_can_read_scoped_evidence(self) -> None:
        server = mcp_server()

        result = server.call_tool(
            "appeal.read_scoped_evidence",
            {
                "agent_role": "evidence_miner",
                "tenant_id": "tenant-demo-mcp",
                "case_id": "case-demo-mcp-read",
                "patient_id": "synthetic-patient-001",
            },
            request_id="read-001",
            at=NOW,
        )

        self.assertEqual(result["decision"], "AUTHORIZED")
        self.assertEqual(result["reference_only"], True)
        self.assertEqual(result["response_content_persisted"], False)
        self.assertEqual(len(server.audit_records), 1)
        self.assertEqual(server.audit_records[0].decision, "AUTHORIZED")

    def test_policy_analyst_chart_read_is_denied_by_registered_capability(self) -> None:
        server = mcp_server()

        result = server.call_tool(
            "appeal.read_scoped_evidence",
            {
                "agent_role": "policy_analyst",
                "tenant_id": "tenant-demo-mcp",
                "case_id": "case-demo-mcp-denied-read",
                "patient_id": "synthetic-patient-001",
            },
            request_id="read-002",
            at=NOW,
        )

        self.assertEqual(result["decision"], "DENIED")
        self.assertEqual(result["reason_code"], "capability_not_in_registered_scope")
        self.assertEqual(result["required_capability"], "clinical-chart.read")
        self.assertEqual(server.audit_records[0].required_scope, "scoped_fhir_chart")

    def test_policy_analyst_mutation_is_denied_and_gate_is_not_discoverable(self) -> None:
        server = mcp_server()

        result = server.call_tool(
            "appeal.request_external_mutation",
            {
                "agent_role": "policy_analyst",
                "tenant_id": "tenant-demo-mcp",
                "case_id": "case-demo-mcp-denied-mutation",
                "clinician_approved": True,
                "vetoes_clear": True,
                "deadline_valid": True,
                "idempotency_key": "case-demo-mcp-denied-mutation:level-1",
            },
            request_id="mutation-001",
            at=NOW,
        )

        self.assertEqual(result["decision"], "DENIED")
        self.assertEqual(result["reason_code"], "capability_not_in_registered_scope")
        self.assertEqual(result["mutation"], True)
        self.assertNotIn("appeal.request_external_mutation", {tool["name"] for tool in server.list_tools()})

    def test_submission_gate_authorization_is_internal_and_does_not_execute(self) -> None:
        server = mcp_server()

        result = server.call_tool(
            "appeal.request_external_mutation",
            {
                "agent_role": "submission_gate",
                "tenant_id": "tenant-demo-mcp",
                "case_id": "case-demo-mcp-gated",
                "clinician_approved": True,
                "vetoes_clear": True,
                "deadline_valid": True,
                "idempotency_key": "case-demo-mcp-gated:level-1",
            },
            request_id="mutation-002",
            at=NOW,
        )

        self.assertEqual(result["decision"], "AUTHORIZED")
        self.assertEqual(result["execution"], "not_executed")
        self.assertEqual(result["mutation_count"], 0)
        self.assertEqual(server.audit_records[0].agent_role, "submission_gate")

    def test_json_rpc_and_http_require_transport_principal(self) -> None:
        server = mcp_server()
        rpc = McpJsonRpcServer(server)

        initialized = rpc.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(initialized["result"]["serverInfo"]["name"], "appeal-mcp")  # type: ignore[index]
        listed = rpc.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(len(listed["result"]["tools"]), 7)  # type: ignore[index]
        denied_without_principal = rpc.handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "appeal.read_scoped_evidence",
                    "arguments": {
                        "tenant_id": "tenant-demo-mcp",
                        "case_id": "case-demo-mcp-rpc",
                        "patient_id": "synthetic-patient-001",
                    },
                },
            }
        )
        self.assertEqual(denied_without_principal["error"]["code"], -32602)  # type: ignore[index]

        api = McpHttpApi(rpc)
        status, body = api.handle("POST", "/mcp", {"jsonrpc": "2.0", "id": 4, "method": "ping"})
        self.assertEqual(status, 200)
        self.assertEqual(body["result"], {})
        status, body = api.handle(
            "POST",
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "appeal.read_scoped_evidence",
                    "arguments": {
                        "tenant_id": "tenant-demo-mcp",
                        "case_id": "case-demo-mcp-http-no-principal",
                        "patient_id": "synthetic-patient-001",
                    },
                },
            },
        )
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "authenticated_agent_principal_required")
        status, body = api.handle(
            "POST",
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "appeal.read_scoped_evidence",
                    "arguments": {
                        "tenant_id": "tenant-demo-mcp",
                        "case_id": "case-demo-mcp-http",
                        "patient_id": "synthetic-patient-001",
                    },
                },
            },
            headers={"X-Appeal-Agent-Role": "evidence_miner"},
            at=NOW,
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["result"]["isError"], False)  # type: ignore[index]

        verified_api = McpHttpApi(
            rpc,
            principal_bindings={"evidence_miner": "evidence-miner@example.invalid"},
            audience="https://appeal-mcp.example.invalid",
        )
        status, body = verified_api.handle(
            "POST",
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "appeal.read_scoped_evidence",
                    "arguments": {
                        "tenant_id": "tenant-demo-mcp",
                        "case_id": "case-demo-mcp-header-ignored",
                        "patient_id": "synthetic-patient-001",
                    },
                },
            },
            headers={"X-Appeal-Agent-Role": "evidence_miner"},
            at=NOW,
        )
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "authenticated_agent_principal_required")

    def test_audit_records_are_aggregate_only(self) -> None:
        server = mcp_server()
        server.call_tool(
            "appeal.read_scoped_evidence",
            {
                "agent_role": "policy_analyst",
                "tenant_id": "tenant-demo-mcp",
                "case_id": "case-demo-mcp-audit",
                "patient_id": "synthetic-patient-001",
            },
            at=NOW,
        )
        serialized = json.dumps(server.audit_json(), sort_keys=True).lower()

        self.assertNotIn('"patient_id"', serialized)
        self.assertNotIn('"prompt"', serialized)
        self.assertNotIn('"raw"', serialized)
        self.assertNotIn('"text"', serialized)


if __name__ == "__main__":
    unittest.main()
