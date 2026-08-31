"""Deploy the synthetic Appeal ADK fleet to Agent Runtime.

This script creates one managed Agent Runtime application containing the seven
role graph. The deterministic Appeal control plane remains authoritative for
state, evidence, security, clinician approval, and external mutation. The
deployment and query report stores resource metadata and aggregate event
counts only; it never stores model response content.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from collections.abc import AsyncIterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from appeal_agents.adk_workflow import (
    MCP_GOVERNANCE_PROBE_MARKER,
    MCP_GOVERNANCE_PROBE_STATE_KEY,
    build_adk_workflow,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = "onyx-yeti-506606-i9"
DEFAULT_LOCATION = "europe-west2"
DEFAULT_MODEL = (
    "projects/onyx-yeti-506606-i9/locations/global/"
    "publishers/google/models/gemini-3.7-flash"
)
DEFAULT_BUCKET = "gs://appeal-agent-staging-onyx-yeti-506606-i9"
DEFAULT_OUTPUT = ROOT / "evidence" / "agent-runtime-deployment.json"
DEFAULT_DISPLAY_NAME = "Appeal Agent Fleet"
DEFAULT_USER_ID = "synthetic-agent-runtime-smoke"
DEFAULT_GATEWAY = "projects/onyx-yeti-506606-i9/locations/europe-west2/agentGateways/appeal-agent-gateway"
DEFAULT_MCP_SERVER = "projects/onyx-yeti-506606-i9/locations/europe-west2/mcpServers/agentregistry-00000000-0000-0000-fe79-effa5b933d5a"
DEFAULT_MCP_INVOKER = "appeal-mcp-invoker@onyx-yeti-506606-i9.iam.gserviceaccount.com"
DEFAULT_MCP_AUDIENCE = "https://appeal-mcp-hhcjpefk2q-nw.a.run.app"


def _git_revision() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def _resource_value(resource: Any, *names: str) -> str | None:
    for name in names:
        value = getattr(resource, name, None)
        if value is not None and str(value):
            return str(value)
    return None


def _event_author(event: Any) -> str | None:
    if isinstance(event, Mapping):
        value = event.get("author")
    else:
        value = getattr(event, "author", None)
    return value if isinstance(value, str) and value else None


def _event_state_delta(event: Any) -> Mapping[str, object]:
    actions = event.get("actions") if isinstance(event, Mapping) else getattr(event, "actions", None)
    if actions is None:
        return {}
    state_delta = (
        actions.get("state_delta")
        if isinstance(actions, Mapping)
        else getattr(actions, "state_delta", None)
    )
    return state_delta if isinstance(state_delta, Mapping) else {}


async def _query_remote(remote_agent: Any) -> dict[str, Any]:
    authors: set[str] = set()
    error_codes: set[str] = set()
    governance_probe: Mapping[str, object] | None = None
    event_count = 0
    stream = remote_agent.async_stream_query(
        user_id=DEFAULT_USER_ID,
        message=(
            f"{MCP_GOVERNANCE_PROBE_MARKER}. Synthetic Appeal Agent Runtime "
            "MCP smoke only. No real patient, "
            "denial, chart, or payer data is present. Ask Evidence Miner to "
            "call the registered scoped-evidence MCP tool exactly once with "
            "tenant_id tenant-demo-agent-gateway-mcp, case_id "
            "case-demo-agent-gateway-mcp, and patient_id "
            "patient-demo-agent-gateway-mcp. Return one concise advisory "
            "note based only on the reference-only result. Do not approve or "
            "file an appeal. The deterministic governance node, not the "
            "model, will invoke the non-executing mutation canary."
        ),
    )
    if not isinstance(stream, AsyncIterable):
        raise TypeError("Agent Runtime query did not return an async stream")
    async for event in stream:
        event_count += 1
        author = _event_author(event)
        if author:
            authors.add(author)
        error_code = (
            event.get("error_code")
            if isinstance(event, Mapping)
            else getattr(event, "error_code", None)
        )
        if isinstance(error_code, str) and error_code:
            error_codes.add(error_code)
        state_delta = _event_state_delta(event)
        probe_value = state_delta.get(MCP_GOVERNANCE_PROBE_STATE_KEY)
        if isinstance(probe_value, Mapping):
            governance_probe = probe_value
    return {
        "query_user_id": DEFAULT_USER_ID,
        "query_event_count": event_count,
        "query_authors": sorted(authors),
        "query_error_codes": sorted(error_codes),
        "query_succeeded": not error_codes and governance_probe is not None,
        "governance_probe": dict(governance_probe or {}),
        "response_content_persisted": False,
    }


def _resource_metadata(remote_agent: Any) -> dict[str, Any]:
    api_resource = getattr(remote_agent, "api_resource", None)
    spec = getattr(api_resource, "spec", None)
    return {
        "resource_name": _resource_value(api_resource, "name"),
        "effective_identity": _resource_value(
            spec, "effective_identity", "effectiveIdentity"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT", DEFAULT_PROJECT))
    parser.add_argument(
        "--location", default=os.getenv("GOOGLE_CLOUD_LOCATION", DEFAULT_LOCATION)
    )
    parser.add_argument("--model", default=os.getenv("APPEAL_GEMINI_MODEL", DEFAULT_MODEL))
    parser.add_argument("--staging-bucket", default=os.getenv("APPEAL_AGENT_STAGING_BUCKET", DEFAULT_BUCKET))
    parser.add_argument("--display-name", default=DEFAULT_DISPLAY_NAME)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-query", action="store_true")
    parser.add_argument(
        "--existing-resource",
        default=os.getenv("APPEAL_AGENT_RUNTIME_RESOURCE"),
        help="Update this existing Runtime resource instead of creating a new one.",
    )
    parser.add_argument(
        "--agent-gateway",
        default=os.getenv("APPEAL_AGENT_GATEWAY", DEFAULT_GATEWAY),
    )
    parser.add_argument(
        "--mcp-server-resource",
        default=os.getenv("APPEAL_MCP_SERVER_RESOURCE", DEFAULT_MCP_SERVER),
    )
    parser.add_argument(
        "--mcp-invoker-service-account",
        default=os.getenv("APPEAL_MCP_INVOKER_SERVICE_ACCOUNT", DEFAULT_MCP_INVOKER),
    )
    parser.add_argument(
        "--mcp-audience",
        default=os.getenv("APPEAL_MCP_AUDIENCE", DEFAULT_MCP_AUDIENCE),
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    os.environ["GOOGLE_CLOUD_PROJECT"] = args.project
    os.environ["GOOGLE_CLOUD_LOCATION"] = args.location
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"

    import vertexai
    from vertexai import agent_engines, types

    # The package uploader archives ``extra_packages`` with their local path
    # prefix.  The old graph did not retain any Appeal-defined runtime class,
    # but the MCP header provider is part of the serialized ADK graph.  Mark
    # that small integration module for by-value cloudpickle serialization so
    # the managed control plane does not need the workstation's ``src`` path
    # in its import path.
    import cloudpickle
    import appeal_agents.adk_workflow as adk_workflow_module

    cloudpickle.register_pickle_by_value(adk_workflow_module)

    client = vertexai.Client(
        project=args.project,
        location=args.location,
        http_options={"api_version": "v1beta1"},
    )
    app = agent_engines.AdkApp(
        agent=build_adk_workflow(
            model=args.model,
            mcp_server_resource=args.mcp_server_resource,
            mcp_project=args.project,
            mcp_location=args.location,
            mcp_invoker_service_account=args.mcp_invoker_service_account,
            mcp_audience=args.mcp_audience,
        ),
        enable_tracing=True,
    )
    runtime_config = {
        "display_name": args.display_name,
        "description": (
            "Synthetic Appeal seven-role ADK workflow. Gemini provides "
            "advisory outputs; deterministic controls and clinician "
            "approval govern every filing decision."
        ),
        "requirements": [
            "google-cloud-aiplatform[agent_engines,adk]>=1.165.1,<2.0.0",
            "google-adk[mcp,agent-identity,a2a]>=2.8.0,<3.0.0",
            "pydantic>=2.0.0,<3.0.0",
            "cloudpickle>=3.0.0,<4.0.0",
        ],
        "staging_bucket": args.staging_bucket,
        "extra_packages": [str(ROOT / "src")],
        "identity_type": types.IdentityType.AGENT_IDENTITY,
        "agent_gateway_config": {
            "agent_to_anywhere_config": {"agent_gateway": args.agent_gateway}
        },
        "env_vars": {
            "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
            # The Runtime resource and Registry remain in europe-west2, while
            # Gemini 3.7 Flash generation uses its documented global endpoint.
            "GOOGLE_CLOUD_LOCATION": "global",
            "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
            "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": "False",
            "APPEAL_GEMINI_MODEL": args.model,
            "APPEAL_MCP_SERVER_RESOURCE": args.mcp_server_resource,
            "APPEAL_MCP_INVOKER_SERVICE_ACCOUNT": args.mcp_invoker_service_account,
            "APPEAL_MCP_AUDIENCE": args.mcp_audience,
        },
        "min_instances": 0,
        "max_instances": 1,
        "resource_limits": {"cpu": "1", "memory": "2Gi"},
    }
    if args.existing_resource:
        runtime_config.pop("identity_type", None)
        runtime_config.pop("agent_gateway_config", None)
        remote_agent = client.agent_engines.update(
            name=args.existing_resource,
            agent=app,
            config=runtime_config,
        )
    else:
        remote_agent = client.agent_engines.create(agent=app, config=runtime_config)

    report: dict[str, Any] = {
        "schema_version": "0.1",
        "recorded_at": datetime.now(UTC).isoformat(),
        "project_id": args.project,
        "location": args.location,
        "display_name": args.display_name,
        "framework": "google-adk",
        "adk_model": args.model,
        "identity_type": "AGENT_IDENTITY",
        "runtime": "agent_runtime",
        "min_instances": 0,
        "max_instances": 1,
        "resource_limits": {"cpu": "1", "memory": "2Gi"},
        "staging_bucket": args.staging_bucket,
        "source_package": "src",
        "source_commit": _git_revision(),
        "synthetic_only": True,
        "response_content_persisted": False,
        "managed_memory_bank_requested": True,
        "managed_observability_requested": True,
        "managed_gateway_configured": True,
        "agent_gateway": args.agent_gateway,
        "mcp_server_resource": args.mcp_server_resource,
        "mcp_invoker_service_account": args.mcp_invoker_service_account,
        "mcp_audience": args.mcp_audience,
        "mcp_toolset_attached_to": ["evidence_miner"],
        "existing_resource_updated": bool(args.existing_resource),
        **_resource_metadata(remote_agent),
    }
    smoke_succeeded = True
    if not args.skip_query:
        smoke = asyncio.run(_query_remote(remote_agent))
        report["smoke"] = smoke
        smoke_succeeded = smoke["query_succeeded"] is True
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if smoke_succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
