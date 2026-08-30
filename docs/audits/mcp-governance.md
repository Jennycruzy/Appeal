# MCP governance audit

Recorded: 2026-08-29

The Appeal MCP service is deployed privately on Cloud Run in `europe-west2`:

```text
projects/onyx-yeti-506606-i9/locations/europe-west2/services/appeal-mcp
revision: appeal-mcp-00005-6mv
url: https://appeal-mcp-hhcjpefk2q-nw.a.run.app/api/mcp
```

The service runs with the dedicated
`appeal-mcp@onyx-yeti-506606-i9.iam.gserviceaccount.com` service account. The
Cloud Run service accepts only authenticated requests. Tool calls are mapped
from verified Google ID-token email claims to the seven registered Appeal
agent identities; the caller cannot choose an agent role with a request
header. All seven identities have `roles/run.invoker`, while the probe user
can mint their tokens only through explicit service-account impersonation
bindings.

The MCP service is registered in the regional Agent Registry as:

```text
projects/onyx-yeti-506606-i9/locations/europe-west2/mcpServers/agentregistry-00000000-0000-0000-fe79-effa5b933d5a
```

Its published tool specification contains six read-only tools. The
Submission Gate mutation seam is intentionally absent from `tools/list` and
never executes a mutation through MCP. The manifest is
[`config/mcp_tools.json`](../../config/mcp_tools.json).

## Live synthetic probe

The probe used real service-account ID tokens and no custom role header:

- Evidence Miner called `appeal.read_scoped_evidence` and was **AUTHORIZED**.
- Policy Analyst called the same patient-scoped tool and was **DENIED** with
  `capability_not_in_registered_scope` for `clinical-chart.read`.
- Policy Analyst called the hidden external-mutation seam and was **DENIED**
  with `capability_not_in_registered_scope` for `external.mutation`.
- The response was reference-only, no response content was persisted, and the
  mutation count was zero.

The complete aggregate response and deployment identity are recorded in
[`evidence/mcp-governance-live.json`](../../evidence/mcp-governance-live.json).

## Boundary and next gate

This probe proves the private Cloud Run identity boundary, Registry tool
catalog, verified-principal mapping, and application capability enforcement.
It was a direct authenticated Cloud Run probe; it did **not** traverse the
Agent Gateway. The separate Gateway/IAP extension therefore remains
`DRY_RUN`/fail-open until the MCP endpoint is routed through that policy path
and its audit records attribute both the authorized read and denied mutation.

No external payer or submission mutation was attempted. The next governance
step is to register the seven agent service records, connect the MCP path to
the Gateway policy where required, run the gateway-routed probe, inspect the
logs, and only then consider enforcement promotion.

On 2026-08-30, the managed Runtime successfully reached this registered MCP
resource through Agent Gateway. Gateway attributed and allowed the MCP
`initialize`, `notifications/initialized`, and `tools/list` methods, and the
private Cloud Run service returned HTTP 200. No `tools/call` followed, so the
routed authorized-read/denied-mutation acceptance test remains open. This
checkpoint does not justify enforcement promotion.
