"""Run the aggregate-only MCP smoke against an existing Agent Runtime."""

from __future__ import annotations

import asyncio
import json
import os

from deploy_agent_runtime import (
    DEFAULT_LOCATION,
    DEFAULT_PROJECT,
    _query_remote,
)


DEFAULT_RESOURCE = (
    "projects/835653516606/locations/europe-west2/"
    "reasoningEngines/936968624818618368"
)


def main() -> int:
    import vertexai

    project = os.getenv("GOOGLE_CLOUD_PROJECT", DEFAULT_PROJECT)
    location = os.getenv("GOOGLE_CLOUD_LOCATION", DEFAULT_LOCATION)
    resource = os.getenv("APPEAL_AGENT_RUNTIME_RESOURCE", DEFAULT_RESOURCE)
    client = vertexai.Client(
        project=project,
        location=location,
        http_options={"api_version": "v1beta1"},
    )
    remote_agent = client.agent_engines.get(name=resource)
    result = asyncio.run(_query_remote(remote_agent))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["query_succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
