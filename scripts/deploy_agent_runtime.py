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

from appeal_agents.adk_workflow import build_adk_workflow


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = "onyx-yeti-506606-i9"
DEFAULT_LOCATION = "europe-west2"
DEFAULT_MODEL = "gemini-3.7-flash"
DEFAULT_BUCKET = "gs://appeal-agent-staging-onyx-yeti-506606-i9"
DEFAULT_OUTPUT = ROOT / "evidence" / "agent-runtime-deployment.json"
DEFAULT_DISPLAY_NAME = "Appeal Agent Fleet"
DEFAULT_USER_ID = "synthetic-agent-runtime-smoke"


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


async def _query_remote(remote_agent: Any) -> dict[str, Any]:
    authors: set[str] = set()
    event_count = 0
    stream = remote_agent.async_stream_query(
        user_id=DEFAULT_USER_ID,
        message=(
            "Synthetic Appeal Agent Runtime smoke only. No patient, denial, "
            "chart, or payer data is present. Return one concise advisory "
            "note and do not approve or file an appeal."
        ),
    )
    if not isinstance(stream, AsyncIterable):
        raise TypeError("Agent Runtime query did not return an async stream")
    async for event in stream:
        event_count += 1
        author = _event_author(event)
        if author:
            authors.add(author)
    return {
        "query_user_id": DEFAULT_USER_ID,
        "query_event_count": event_count,
        "query_authors": sorted(authors),
        "response_content_persisted": False,
    }


def _resource_metadata(remote_agent: Any) -> dict[str, Any]:
    api_resource = getattr(remote_agent, "api_resource", None)
    spec = getattr(api_resource, "spec", None)
    return {
        "resource_name": _resource_value(remote_agent, "name", "resource_name"),
        "effective_identity": _resource_value(
            spec, "effective_identity", "effectiveIdentity"
        ),
        "resource_state": _resource_value(
            api_resource, "state", "resource_state"
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
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    os.environ["GOOGLE_CLOUD_PROJECT"] = args.project
    os.environ["GOOGLE_CLOUD_LOCATION"] = args.location
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"

    import vertexai
    from vertexai import agent_engines, types

    client = vertexai.Client(
        project=args.project,
        location=args.location,
        http_options={"api_version": "v1beta1"},
    )
    app = agent_engines.AdkApp(
        agent=build_adk_workflow(model=args.model),
        enable_tracing=True,
    )
    remote_agent = client.agent_engines.create(
        agent=app,
        config={
            "display_name": args.display_name,
            "description": (
                "Synthetic Appeal seven-role ADK workflow. Gemini provides "
                "advisory outputs; deterministic controls and clinician "
                "approval govern every filing decision."
            ),
            "requirements": [
                "google-cloud-aiplatform[agent_engines,adk]>=1.165.1,<2.0.0",
                "google-adk>=2.8.0,<3.0.0",
            ],
            "staging_bucket": args.staging_bucket,
            "extra_packages": [str(ROOT / "src")],
            "identity_type": types.IdentityType.AGENT_IDENTITY,
            "env_vars": {
                "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
                "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
                "APPEAL_GEMINI_MODEL": args.model,
            },
            "min_instances": 0,
            "max_instances": 1,
            "resource_limits": {"cpu": "1", "memory": "2Gi"},
        },
    )

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
        "managed_gateway_configured": False,
        **_resource_metadata(remote_agent),
    }
    if not args.skip_query:
        report["smoke"] = asyncio.run(_query_remote(remote_agent))
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
