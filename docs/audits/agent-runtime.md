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
succeeded with a `case_id` scope. The SDK readback attempt stopped at local
parameter validation before a service read, so Memory Bank retrieval remains
unverified. Telemetry was requested and the project's default global trace
scope exists, but direct trace export remains unverified.

The controlled synthetic Pub/Sub subscriber now invokes this resource for one
allowlisted `intake/clear` checkpoint. Firestore claims the stable event ID,
prevents duplicate delivery from re-running the query, and persists only the
aggregate result. The current revision's invocation evidence is recorded in
[`evidence/agent-runtime-subscriber.json`](../../evidence/agent-runtime-subscriber.json).

This audit proves a managed Agent Runtime, Registry, and Agent Identity
deployment boundary for the seven-role graph plus one controlled synthetic
subscriber invocation. It does not claim Agent Gateway, Agent Policies,
Firebase Auth, broader subscriber-driven workflow execution, a separate payer
service, a hosted console, or a complete Appeal evaluation.
The deployment and all smoke inputs are synthetic and aggregate-only; no real
case data was uploaded.
