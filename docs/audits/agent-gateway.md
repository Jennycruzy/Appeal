# Agent Gateway and Policies audit

Recorded: 2026-08-29

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
- `iamEnforcementMode: DRY_RUN`, `failOpen: true`, and policy version `V1`;
- the `appeal-iap-authz-policy` request-authorization policy; and
- a regional Agent Registry binding for the managed Runtime principal with an
  allow condition requiring read-only, non-destructive, closed-world MCP
  operations.

The raw declarative manifests are under
[`config/agent_gateway/`](../../config/agent_gateway/), and the aggregate
verification record is
[`evidence/agent-gateway-governance.json`](../../evidence/agent-gateway-governance.json).

The two platform destinations observed in the first dry-run were then
registered in the same regional registry and granted endpoint-specific
`roles/iap.egressor` bindings for the managed Agent Identity:

- `europe-west2-aiplatform.mtls.googleapis.com`
- `telemetry.mtls.googleapis.com`

No payer, submission, MCP server, or arbitrary internet destination was
registered.

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

The MCP probe proves the private Cloud Run identity and capability boundary,
but it was direct Cloud Run traffic rather than Gateway-routed traffic. It
does not yet prove Gateway/IAP enforcement of an MCP mutation denial.

Do not switch the extension to `ENFORCE` yet. First route the MCP endpoint
through the policy path, inspect the resulting authorization records, and keep
the current fail-open/dry-run configuration until those checks are recorded.

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
