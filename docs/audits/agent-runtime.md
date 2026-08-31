# Managed Agent Runtime audit

Recorded: 2026-08-29

The seven-role Appeal ADK graph is deployed as a synthetic-only managed Agent
Runtime application in project `onyx-yeti-506606-i9`, region `europe-west2`.
The deployed resource is:

```text
projects/835653516606/locations/europe-west2/reasoningEngines/936968624818618368
```

The application was built from the repository `src` package with Google ADK,
uses Gemini `3.7-flash`, enables runtime tracing, and requests the managed
`AGENT_IDENTITY` deployment type. Its effective runtime identity is:

```text
agents.global.proj-835653516606.system.id.goog/resources/aiplatform/projects/835653516606/locations/europe-west2/reasoningEngines/936968624818618368
```

The application is visible in Agent Registry as `Appeal Agent Fleet` with
framework `google-adk`. A remote synthetic query returned two aggregate
workflow events authored by `appeal_agent_fleet`; no response content was
written to the repository. The registry and runtime metadata are recorded in
[`evidence/agent-runtime-deployment.json`](../../evidence/agent-runtime-deployment.json).

Managed session creation succeeded for the reference-only synthetic user
`synthetic-agent-runtime-smoke`. A reference-only synthetic memory write also
succeeded with a `case_id` scope. Direct Memory Bank retrieval then returned
one matching memory in that scope; only the result count and resource metadata
were retained. Telemetry was requested and the project's default global trace
scope exists. A two-day Cloud Trace complete-view query returned 22 traces,
including two Agent Runtime traces with four spans each and root span
`invoke_workflow appeal_agent_fleet`. No span attributes or response content
were persisted. The aggregate results are recorded in
[`evidence/agent-runtime-deployment.json`](../../evidence/agent-runtime-deployment.json).

The controlled synthetic Pub/Sub subscriber now invokes this resource for one
allowlisted `intake/clear` checkpoint. Firestore claims the stable event ID,
prevents duplicate delivery from re-running the query, and persists only the
aggregate result. The revision-bound invocation evidence is recorded in
[`evidence/agent-runtime-subscriber.json`](../../evidence/agent-runtime-subscriber.json).

This audit proves a managed Agent Runtime, Registry, and Agent Identity
deployment boundary for the seven-role graph plus one controlled synthetic
subscriber invocation. On 2026-08-31, a marker-gated governance node also
completed an enforced Gateway probe: one registered read returned HTTP 200,
and one non-executing destructive canary was denied at Agent Gateway with HTTP
403. Runtime state records the Gateway denial and zero mutations in
[`evidence/agent-runtime-deployment.json`](../../evidence/agent-runtime-deployment.json),
with matching Gateway evidence in
[`evidence/agent-gateway-mcp-enforcement.json`](../../evidence/agent-gateway-mcp-enforcement.json).

The post-fix synthetic deployment smoke completed all seven advisory roles with
no provider error events. This audit does not claim Firebase Auth, broader
subscriber-driven workflow execution, a separate payer service, a hosted
console, or a complete Appeal evaluation.
The deployment and all smoke inputs are synthetic and aggregate-only; no real
case data was uploaded.

## Vertex quota resilience

The managed graph uses Vertex AI through ADC/Agent Identity; it does not use an
AI Studio API key. Vertex HTTP 429 responses are transient shared-capacity or
quota responses, and ADK exposes them as `_ResourceExhaustedError`. Every
advisory role now shares a small request interval to smooth the serial burst,
and a before-model callback configures truncated exponential backoff with
jitter for 408, 429, and 5xx responses. The settings are deployment-time
environment variables:

```text
ADK_GEMINI_MIN_REQUEST_INTERVAL_SECONDS=2
ADK_GEMINI_RETRY_ATTEMPTS=5
ADK_GEMINI_RETRY_INITIAL_DELAY_SECONDS=2
ADK_GEMINI_RETRY_MAX_DELAY_SECONDS=30
ADK_GEMINI_RETRY_JITTER=1
```

The subscriber's default query budget is 120 seconds so a transient provider
response can complete its backoff instead of being cut off at 45 seconds. A
provider error event is treated as a failed delivery and remains eligible for
Pub/Sub redelivery; it is never recorded as a completed Agent Runtime
invocation.
