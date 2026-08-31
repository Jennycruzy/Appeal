"""Synchronize the Appeal MCP tool specification into Agent Registry."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession


API_ROOT = "https://agentregistry.googleapis.com/v1"


def _checked_json(response: Any) -> dict[str, Any]:
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise RuntimeError("Agent Registry returned a non-object response")
    return value


def _wait_for_operation(
    session: AuthorizedSession,
    operation: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_seconds: int = 180,
) -> None:
    name = operation.get("name")
    if not isinstance(name, str) or not name:
        raise RuntimeError("Agent Registry update returned no operation name")
    deadline = time.monotonic() + timeout_seconds
    current = operation
    while not current.get("done"):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Agent Registry update did not complete: {name}")
        time.sleep(2)
        current = _checked_json(session.get(f"{API_ROOT}/{name}", headers=headers))
    if "error" in current:
        raise RuntimeError(f"Agent Registry update failed: {current['error']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-resource", required=True)
    parser.add_argument("--tool-spec", type=Path, required=True)
    args = parser.parse_args()

    tool_document = json.loads(args.tool_spec.read_text(encoding="utf-8"))
    tools = tool_document.get("tools") if isinstance(tool_document, dict) else None
    if not isinstance(tools, list) or not tools:
        raise ValueError("tool specification must contain a non-empty tools list")

    credentials, project_id = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    quota_project = getattr(credentials, "quota_project_id", None) or project_id
    headers = {"x-goog-user-project": quota_project} if quota_project else {}
    session = AuthorizedSession(credentials)
    url = f"{API_ROOT}/{args.service_resource}"
    current = _checked_json(session.get(url, headers=headers))
    desired_spec = {"type": "TOOL_SPEC", "content": {"tools": tools}}
    changed = current.get("mcpServerSpec") != desired_spec
    if changed:
        operation = _checked_json(
            session.patch(
                url,
                headers=headers,
                params={"updateMask": "mcp_server_spec"},
                json={"name": args.service_resource, "mcpServerSpec": desired_spec},
            )
        )
        _wait_for_operation(session, operation, headers=headers)

    verified = _checked_json(session.get(url, headers=headers))
    if verified.get("mcpServerSpec") != desired_spec:
        raise RuntimeError("live Agent Registry tool specification does not match source")
    names = [tool.get("name") for tool in tools if isinstance(tool, dict)]
    print(
        json.dumps(
            {
                "service_resource": args.service_resource,
                "changed": changed,
                "tool_count": len(names),
                "mutation_canary_registered": "appeal.probe_denied_mutation" in names,
                "hidden_mutation_registered": "appeal.request_external_mutation" in names,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
