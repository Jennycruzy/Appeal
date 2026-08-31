from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from collections.abc import Mapping

from appeal_agents.adk_workflow import (
    MCP_GOVERNANCE_PROBE_MARKER,
    MCP_GOVERNANCE_PROBE_STATE_KEY,
    ManagedMcpGovernanceProbe,
)


def rpc_result(decision: str) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": "probe",
        "result": {
            "structuredContent": {
                "decision": decision,
                "mutation_count": 0,
                "response_content_persisted": False,
            }
        },
    }


class ManagedMcpGovernanceProbeTests(unittest.TestCase):
    def test_non_probe_input_is_a_network_free_passthrough(self) -> None:
        requests: list[Mapping[str, object]] = []
        probe = ManagedMcpGovernanceProbe(
            mcp_url="https://mcp.example.invalid/mcp",
            header_provider=lambda _context: (_ for _ in ()).throw(
                AssertionError("header provider must not run")
            ),
            requester=lambda _url, _headers, payload: (
                requests.append(payload) or (200, {})
            ),
        )
        context = SimpleNamespace(state={})

        result = asyncio.run(probe.run(context, "ordinary synthetic workflow input"))

        self.assertEqual(result, "ordinary synthetic workflow input")
        self.assertEqual(requests, [])
        self.assertEqual(context.state, {})

    def test_probe_executes_authorized_read_and_denied_mutation_canary(self) -> None:
        requests: list[Mapping[str, object]] = []

        def requester(
            _url: str,
            _headers: Mapping[str, str],
            payload: Mapping[str, object],
        ) -> tuple[int, object]:
            requests.append(payload)
            params = payload["params"]
            assert isinstance(params, Mapping)
            if params["name"] == "appeal.read_scoped_evidence":
                return 200, rpc_result("AUTHORIZED")
            return 200, rpc_result("DENIED")

        probe = ManagedMcpGovernanceProbe(
            mcp_url="https://mcp.example.invalid/mcp",
            header_provider=lambda _context: {"Authorization": "Bearer synthetic"},
            requester=requester,
        )
        context = SimpleNamespace(state={})
        message = f"{MCP_GOVERNANCE_PROBE_MARKER} synthetic only"

        self.assertEqual(asyncio.run(probe.run(context, message)), message)
        names = []
        for request in requests:
            params = request["params"]
            assert isinstance(params, Mapping)
            names.append(params["name"])
        self.assertEqual(
            names,
            ["appeal.read_scoped_evidence", "appeal.probe_denied_mutation"],
        )
        result = context.state[MCP_GOVERNANCE_PROBE_STATE_KEY]
        self.assertEqual(result["read_decision"], "AUTHORIZED")
        self.assertEqual(result["mutation_decision"], "DENIED")
        self.assertEqual(result["mutation_denial_layer"], "application_capability")
        self.assertEqual(result["mutation_count"], 0)
        self.assertEqual(
            result["mutation_probe_tool"], "appeal.probe_denied_mutation"
        )
        self.assertEqual(result["mutation_probe_discoverable"], True)
        self.assertEqual(result["hidden_mutation_discoverable"], False)

    def test_gateway_denial_is_accepted_without_parsing_response_content(self) -> None:
        calls = 0

        def requester(
            _url: str,
            _headers: Mapping[str, str],
            _payload: Mapping[str, object],
        ) -> tuple[int, object]:
            nonlocal calls
            calls += 1
            return (200, rpc_result("AUTHORIZED")) if calls == 1 else (403, {})

        probe = ManagedMcpGovernanceProbe(
            mcp_url="https://mcp.example.invalid/mcp",
            header_provider=lambda _context: {"Authorization": "Bearer synthetic"},
            requester=requester,
        )
        context = SimpleNamespace(state={})

        asyncio.run(probe.run(context, MCP_GOVERNANCE_PROBE_MARKER))

        result = context.state[MCP_GOVERNANCE_PROBE_STATE_KEY]
        self.assertEqual(result["mutation_denial_layer"], "agent_gateway")
        self.assertEqual(result["mutation_http_status"], 403)
        self.assertEqual(result["mutation_count"], 0)

    def test_probe_fails_closed_on_an_unauthorized_read(self) -> None:
        probe = ManagedMcpGovernanceProbe(
            mcp_url="https://mcp.example.invalid/mcp",
            header_provider=lambda _context: {"Authorization": "Bearer synthetic"},
            requester=lambda _url, _headers, _payload: (200, rpc_result("DENIED")),
        )

        with self.assertRaisesRegex(RuntimeError, "read was not authorized"):
            asyncio.run(
                probe.run(SimpleNamespace(state={}), MCP_GOVERNANCE_PROBE_MARKER)
            )

    def test_nested_transport_denial_is_classified(self) -> None:
        error = ExceptionGroup(
            "stream transport failed",
            [RuntimeError("Client error '403 Forbidden' for MCP request")],
        )

        self.assertEqual(ManagedMcpGovernanceProbe._gateway_denial_status(error), 403)


if __name__ == "__main__":
    unittest.main()
