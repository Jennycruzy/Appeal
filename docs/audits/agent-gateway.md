# Agent Gateway and Policies audit

Recorded: 2026-08-31

The Appeal Agent Fleet now has a Google-managed Agent-to-Anywhere gateway in
`europe-west2`:

```text
projects/onyx-yeti-506606-i9/locations/europe-west2/agentGateways/appeal-agent-gateway
```

The gateway is associated with the regional Agent Registry and uses the MCP
protocol. The existing managed Reasoning Engine is explicitly bound to this
gateway for egress and retains `AGENT_IDENTITY`:

```text
projects/835653516606/locations/europe-west2/reasoningEngines/936968624818618368
```

IAP authorization is attached through:

- the `appeal-iap-authz` Service Extensions authorization extension;
- `iamEnforcementMode: ENFORCE`, `failOpen: false`, and policy version `V1`;
- the `appeal-iap-authz-policy` request-authorization policy; and
- a regional Agent Registry binding for the managed Runtime principal with an
  explicit allow condition containing the six bounded read-tool names and the
  empty base-protocol value.

The raw declarative manifests are under
[`config/agent_gateway/`](../../config/agent_gateway/), and the aggregate
verification record is
[`evidence/agent-gateway-governance.json`](../../evidence/agent-gateway-governance.json).

The platform destinations observed across the dry-run and enforced probes are
registered in the same regional registry and granted endpoint-specific
`roles/iap.egressor` bindings for the managed Agent Identity:

- `europe-west2-aiplatform.mtls.googleapis.com`
- `telemetry.mtls.googleapis.com`
- `aiplatform.mtls.googleapis.com`
- `iamcredentials.mtls.googleapis.com`

The private Appeal MCP server is registered separately as an MCP resource. No
payer, submission, or arbitrary internet destination is registered.

## Synthetic verification

One fresh scalar-only event was published to the existing `appeal-events` topic
for `tenant-demo-agent-gateway /
case-demo-agent-gateway-20260829151856898653`. The authenticated Cloud Run push
returned HTTP 200 on revision `appeal-backend-00017-fxp`. The Firestore
invocation record completed on attempt 1 with two aggregate events authored by
`appeal_agent_fleet`; no response content or real case data was persisted, and
the test performed no external mutation.

During the post-registration gateway window, nineteen gateway request logs were
observed: eighteen HTTP 200 responses and one destination HTTP 404. Fourteen
HTTP requests had authorization result `ALLOWED`; the five CONNECT records did
not carry an authorization result. Every inspected platform request was
associated with one of the two newly registered endpoint resources, and no
`unregisteredEndpoint` appeared in the Gateway records. The 404 was not a
gateway policy denial; it was the same destination response from the synthetic
model call. The requests were routed through the gateway to the regional Agent
Platform and Telemetry hosts.

The earlier pre-registration window contained nine IAP `AuthorizeUser` audit
entries. All nine had `dryRun: true` and identified the destination as
`unregisteredEndpoint`; that historical finding motivated the endpoint
registration. A subsequent broad IAP query did not return a new
`AuthorizeUser` record at capture time, so the post-registration endpoint
association is based on the Gateway records above.

## Boundary and enforcement decision

This proves the gateway binding, dry-run authorization path, endpoint
registration for the observed platform destinations, endpoint-specific egress
permissions, authenticated Pub/Sub delivery, and aggregate-only Runtime
completion. A separate live MCP service and probe now exist; see
[`docs/audits/mcp-governance.md`](mcp-governance.md) and
[`evidence/mcp-governance-live.json`](../../evidence/mcp-governance-live.json).

The earlier direct MCP probe proves the private Cloud Run identity and
capability boundary. The enforced checkpoint below now closes the separate
Gateway proof gap.

## 2026-08-30 routed MCP checkpoint

The managed seven-role Runtime now completes successfully with Gemini 3.7
Flash on the global generation endpoint while the Runtime, Registry, and
Gateway remain in `europe-west2`. The successful run produced seven aggregate
events from all seven role authors and no Runtime error code.

During the Evidence Miner step, Gateway logs attributed the private Cloud Run
destination to the registered MCP server resource. `initialize`,
`notifications/initialized`, and `tools/list` each returned HTTP 200 with an
`ALLOWED` authorization result; the corresponding Cloud Run requests also
returned HTTP 200. The model did not issue `tools/call`, so this is routed MCP
discovery evidence, not yet the required authorized read and denied mutation
evidence. Enforcement remains `DRY_RUN`/fail-open.

## 2026-08-31 enforced MCP checkpoint

The managed Runtime now contains a marker-gated deterministic governance node.
It uses the official MCP session implementation with HTTP keep-alive disabled
so every JSON-RPC message independently traverses Gateway authorization.
Ordinary workflow messages do not invoke this node or mint an MCP token.

Agent Registry publishes six bounded read tools plus
`appeal.probe_denied_mutation`, a destructive-classification canary that is
always denied before application role evaluation and has no external executor.
The real `appeal.request_external_mutation` Submission Gate seam remains absent
from `tools/list`. The IAP condition uses an explicit six-name allowlist, so
authorization does not depend on a fail-open annotation lookup.

The four exact Runtime dependency hosts—regional Agent Platform, global Agent
Platform, IAM Credentials, and Telemetry—are registered. Their endpoint
policies use the numeric-project Agent Identity URI reported by the Runtime.
The authorization extension is now `ENFORCE` with `failOpen: false`.

In the final enforced window, `appeal.read_scoped_evidence` was `ALLOWED`,
returned HTTP 200, and reached the private Cloud Run MCP service.
`appeal.probe_denied_mutation` was `DENIED` by Agent Gateway with HTTP 403 and
did not reach Cloud Run. Runtime state recorded
`mutation_denial_layer: agent_gateway`; mutation count and persisted response
content remained zero.

The matching aggregate record is
[`evidence/agent-gateway-mcp-enforcement.json`](../../evidence/agent-gateway-mcp-enforcement.json).
Gemini later returned `_ResourceExhaustedError` during the advisory portion of
the deployment smoke. That post-governance quota failure is recorded separately
and does not change the completed Gateway allow/deny proof.
