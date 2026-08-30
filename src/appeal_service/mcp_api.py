"""HTTP adapter for the Appeal MCP JSON-RPC server."""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from collections.abc import Callable, Mapping
from typing import cast

from appeal_platform import McpJsonRpcServer


class McpHttpApi:
    """Expose MCP over one authenticated JSON endpoint.

    The upstream Gateway/IAM boundary authenticates the caller. The adapter
    requires the resulting agent-role header and never trusts an agent role
    supplied inside tool arguments when a transport principal is available.
    """

    def __init__(
        self,
        server: McpJsonRpcServer,
        *,
        principal_header: str = "x-appeal-agent-role",
        principal_bindings: Mapping[str, str] | None = None,
        principal_aliases: Mapping[str, str] | None = None,
        audience: str | None = None,
    ) -> None:
        self.server = server
        self.principal_header = principal_header.lower()
        self.principal_bindings = dict(principal_bindings or {})
        # Aliases are transport identities that are intentionally mapped to a
        # registered role for a managed Runtime bridge. They are separate from
        # the seven human-readable service-account bindings so the direct
        # per-agent probe remains valid as well.
        self.principal_aliases = dict(principal_aliases or {})
        self.audience = audience
        if self.principal_bindings and not self.audience:
            raise ValueError("MCP identity bindings require an ID-token audience")

    def handle(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
        *,
        at: datetime | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, object]]:
        normalized_path = path.split("?", 1)[0].rstrip("/") or "/"
        if method.upper() == "GET" and normalized_path in {"/healthz", "/api/healthz"}:
            return 200, {
                "status": "ok",
                "protocol": "mcp-json-rpc",
                "server": "appeal-mcp",
                "tool_count": len(self.server.tools.list_tools()),
                "mutation_tool_discoverable": False,
                "principal_header_required_for_tool_calls": True,
                "transport_identity_mode": ("verified_id_token" if self.principal_bindings else "synthetic_header"),
                "synthetic_only": True,
            }
        if method.upper() != "POST" or normalized_path not in {"/mcp", "/api/mcp"}:
            return 404, {"error": "not_found"}
        if payload is None:
            return 400, {"error": "json_rpc_object_required"}
        principal = self._principal(headers or {})
        if payload.get("method") == "tools/call" and principal is None:
            return 401, {"error": "authenticated_agent_principal_required"}
        return 200, self.server.handle(payload, principal_role=principal, at=at)

    def _principal(self, headers: Mapping[str, str]) -> str | None:
        if self.principal_bindings:
            authorization = next(
                (value for key, value in headers.items() if key.lower() == "authorization"),
                "",
            )
            if not authorization.startswith("Bearer "):
                return None
            token = authorization.removeprefix("Bearer ").strip()
            if not token or self.audience is None:
                return None
            try:
                id_token = importlib.import_module("google.oauth2.id_token")
                requests = importlib.import_module("google.auth.transport.requests")
                verifier = cast(Callable[..., object], getattr(id_token, "verify_oauth2_token"))
                request_factory = cast(Callable[[], object], getattr(requests, "Request"))
                claims = verifier(token, request_factory(), audience=self.audience)
            except Exception:
                return None
            if not isinstance(claims, Mapping):
                return None
            email = claims.get("email")
            if not isinstance(email, str):
                return None
            role = next(
                (role for role, principal in self.principal_bindings.items() if principal == email),
                None,
            )
            return role or self.principal_aliases.get(email)
        for key, value in headers.items():
            if key.lower() == self.principal_header and value.strip():
                return value.strip()
        return None


__all__ = ["McpHttpApi"]
