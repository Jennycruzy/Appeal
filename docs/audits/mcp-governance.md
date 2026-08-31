# MCP governance audit

Recorded: 2026-08-31

The Appeal MCP service is deployed privately on Cloud Run in `europe-west2`:

```text
projects/onyx-yeti-506606-i9/locations/europe-west2/services/appeal-mcp
revision: appeal-mcp-00007-5qn
url: https://appeal-mcp-hhcjpefk2q-nw.a.run.app/mcp
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

Its published tool specification contains six read-only tools and one
destructive governance canary. The canary is structurally non-executing and
always denied by the application if reached. The real Submission Gate mutation
seam is intentionally absent from `tools/list` and never executes a mutation
through MCP. The manifest is
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

## Enforced Gateway probe

The direct probe above proves the private Cloud Run identity boundary,
verified-principal mapping, and application capability enforcement. A separate
managed Runtime probe now proves the Gateway boundary under
`ENFORCE`/fail-closed operation:

- the registered scoped-evidence read was allowed with HTTP 200;
- the registered destructive canary was denied by Gateway with HTTP 403;
- Cloud Run received the read but not the denied canary;
- the real Submission Gate mutation remained hidden; and
- no mutation or response content was persisted.

The aggregate enforced record is
[`evidence/agent-gateway-mcp-enforcement.json`](../../evidence/agent-gateway-mcp-enforcement.json).
No payer or submission mutation was attempted.
