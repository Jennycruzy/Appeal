"""Run the synthetic-only Appeal MCP server for a Cloud Run service."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

from appeal_agents import default_policy_registry
from appeal_platform import AgentRegistry, McpJsonRpcServer, McpToolServer
from appeal_service import McpHttpApi


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "config" / "agent_registry.json"


def build_api(registry_path: Path = DEFAULT_REGISTRY) -> McpHttpApi:
    registry = AgentRegistry.from_path(registry_path)
    policies = default_policy_registry()
    identity_mode = os.getenv("MCP_IDENTITY_MODE", "verified").strip().lower()
    if identity_mode not in {"verified", "header"}:
        raise ValueError("MCP_IDENTITY_MODE must be verified or header")
    runtime_principal = os.getenv("MCP_RUNTIME_INVOKER_PRINCIPAL", "").strip()
    runtime_role = os.getenv("MCP_RUNTIME_INVOKER_ROLE", "evidence_miner").strip()
    if bool(runtime_principal) != bool(runtime_role):
        raise ValueError(
            "MCP_RUNTIME_INVOKER_PRINCIPAL and MCP_RUNTIME_INVOKER_ROLE "
            "must be configured together"
        )
    return McpHttpApi(
        McpJsonRpcServer(McpToolServer(registry, policies)),
        principal_bindings=(registry.principals() if identity_mode == "verified" else None),
        principal_aliases=(
            {runtime_principal: runtime_role}
            if identity_mode == "verified" and runtime_principal
            else None
        ),
        audience=(os.getenv("MCP_AUDIENCE", "").strip() if identity_mode == "verified" else None),
    )


def serve(host: str, port: int, registry_path: Path) -> None:
    api = build_api(registry_path)

    class Handler(BaseHTTPRequestHandler):
        def _respond(self, status: int, value: dict[str, object]) -> None:
            body = json.dumps(value, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            status, value = api.handle("GET", self.path, headers=dict(self.headers.items()))
            self._respond(status, value)

        def do_POST(self) -> None:  # noqa: N802
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._respond(400, {"error": "invalid_content_length"})
                return
            if length > 64 * 1024:
                self._respond(413, {"error": "request_too_large"})
                return
            try:
                raw = self.rfile.read(length)
                parsed: object = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._respond(400, {"error": "invalid_json"})
                return
            if not isinstance(parsed, dict):
                self._respond(400, {"error": "json_rpc_object_required"})
                return
            status, value = api.handle(
                "POST",
                self.path,
                cast(dict[str, object], parsed),
                at=datetime.now(UTC),
                headers=dict(self.headers.items()),
            )
            self._respond(status, value)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Appeal MCP server listening on http://{host}:{port}/mcp")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8080")))
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    args = parser.parse_args()
    serve(args.host, args.port, args.registry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
