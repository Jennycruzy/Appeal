# Current limitations

This file records missing or unverified capabilities. It is intentionally
updated as the product is built; no missing feature is described elsewhere as
complete.

## Product and model integrations

- A synthetic seven-agent ADK workflow smoke run succeeded against Vertex AI
  using Gemini `3.7-flash` at the global endpoint: seven events, all seven
  named agents, and zero provider errors. The aggregate result is recorded in
  [`evidence/adk-workflow-smoke.json`](../evidence/adk-workflow-smoke.json).
  This proves provider/runtime execution only; it is not a complete appeal
  case run or a production deployment. Google ADK `2.8.0` is installed in the
  project `.venv`, and the graph wiring is present behind
  `src/appeal_agents/adk_workflow.py`.
- A synthetic-only Cloud Run service is deployed in project
  `onyx-yeti-506606-i9`, region `europe-west2`, revision
  `appeal-backend-00017-fxp`. Its health endpoint, Firestore-backed state,
  managed Model Armor -> Gemma boundary, and synthetic case lifecycle were
  verified; the aggregate record is
  [`evidence/cloud-run-deployment.json`](../evidence/cloud-run-deployment.json).
  The service is unauthenticated and synthetic-only, accepts no real case
  data, and is not a production API. Reference-only workflow sessions and
  hash-chained receipts were verified across Cloud Run revision replacement.
- A real synthetic ADK `Runner` execution completed through all seven named
  roles using an image-only PDF input and Gemini `3.7-flash`. Its aggregate
  Stage B exit is recorded in
  [`evidence/adk-stage-b-case-exit.json`](../evidence/adk-stage-b-case-exit.json).
  This proves the ADK/Gemini provider path and multimodal input path for one
  synthetic case; the Cloud Run service remains a deterministic facade. The
  seven-role graph is now also deployed to managed Agent Runtime with Agent
  Registry and Agent Identity metadata. The aggregate runtime record is
  [`evidence/agent-runtime-deployment.json`](../evidence/agent-runtime-deployment.json)
  and the audit is in [`docs/audits/agent-runtime.md`](audits/agent-runtime.md).
- Managed Agent Runtime session creation and a reference-only synthetic
  Memory Bank write succeeded. Direct retrieval returned one memory in the
  synthetic `case_id` scope without persisting its fact content in the report.
  Telemetry was requested and Cloud Trace returned two matching Agent Runtime
  traces in the two-day verification window. A regional Agent Gateway and IAP
  Agent Policies now run in `ENFORCE`/fail-closed mode. Four exact managed
  Runtime dependency hosts and the MCP server are registered with
  endpoint-specific egress permissions. A registered read was allowed and a
  non-executing destructive canary was denied by Gateway with HTTP 403; the
  real Submission Gate mutation remains hidden. The latest advisory sequence
  hit Gemini `_ResourceExhaustedError` after governance completed, so it is not
  a clean seven-role smoke. Firebase Auth and broader
  subscriber-driven Agent Runtime workflow execution are also not yet
  deployed. The advisory quota failure was observed before the Vertex
  resilience settings were deployed; it remains an operational condition to
  re-verify, not an authentication or gateway-enforcement failure. The
  governance audit is in
  [`docs/audits/agent-gateway.md`](audits/agent-gateway.md), with aggregate
  evidence in
  [`evidence/agent-gateway-governance.json`](../evidence/agent-gateway-governance.json).
  A controlled synthetic subscriber checkpoint is implemented and verified on
  the current revision; its aggregate record is
  [`evidence/agent-runtime-subscriber.json`](../evidence/agent-runtime-subscriber.json).
  Native Firestore case state, reference-only workflow-session persistence,
  hash-chained receipt persistence, and the managed Model Armor -> Gemma
  boundary are deployed for the Cloud Run service. The managed
  Pub/Sub topic and authenticated push subscription are also deployed; the
  aggregate proof is in
  [`evidence/cloud-run-deployment.json`](../evidence/cloud-run-deployment.json)
  and the audit is in [`docs/audits/cloud-persistence.md`](audits/cloud-persistence.md).
  The hosted security integration audit is in
  [`docs/audits/managed-security-cloud-run.md`](audits/managed-security-cloud-run.md).
  Local fallback seams for event delivery, scoped memory, payer adjudication,
  and reversibility are present under `src/appeal_platform/`.
- The current seven-agent implementation demonstrates the role boundaries and
  governance contracts. The ADK case exit is a synthetic provider exercise;
  the deployed Cloud Run container exposes the deterministic API facade with
  Firestore case metadata, not a complete real-case Gemini-backed appeal
  evaluation.

## Data and evaluation

- The accepted CMS QIC data is a regulator-summary benchmark, not a complete
  Appeal case corpus.
- The scoring handoff is intentionally deferred until the agent workflow is
  complete. No benchmark score has been produced.
- Completed full Appeal evaluations remain zero because no complete authorized
  case package is present.
- A Gemini-derived criterion corpus and hand-validated agreement rate have
  not yet been produced in this workspace.
- Synthea is synthetic and cannot supply real-denial ground truth.

## Operational features

- The repository does not yet provide a web console or Firebase
  authentication. Cloud Scheduler now invokes the protected Deadline
  Sentinel route hourly; Cloud Run case state, safe references,
  reference-only workflow sessions, and hash-chained receipts are persisted in
  Firestore, and reference-only workflow events publish through the managed
  Pub/Sub topic. The managed Agent Runtime has a separately verified
  reference-only session and Memory Bank write, and one allowlisted synthetic
  Pub/Sub checkpoint invokes it with Firestore idempotency. Memory Bank
  retrieval and the corresponding Cloud Trace export are verified only for
  synthetic probes; this is not a complete asynchronous Appeal workflow. The
  endpoint is synthetic-only and intentionally not a production deployment.
- The local event spine records and deduplicates workflow events, but the
  deterministic workflow still invokes role adapters in-process. The managed
  subscriber adapter is limited to one synthetic `intake/clear` checkpoint and
  does not yet replace the in-process workflow.
- `LocalAppealService` is an in-process case-board facade for testing the
  lifecycle; it is not an authenticated network API.
- `scripts/run_local_api.py` exposes that facade on loopback for local
  integration testing only. It has no Firebase/Auth/IAM protection and must
  not be treated as a production or public endpoint.
- Multimodal scanned-document extraction is not yet connected to Gemini's
  vision path. A local fixture may carry a document media type and a bounded
  extraction adapter, but that is not evidence of a live vision deployment.
- External submission and withdrawal are not connected to a payer. The local
  submission gate can prove idempotent decision logic and receipt generation;
  it does not file a real appeal.
- The local reversibility ledger records a compensating action, but it is not
  yet connected to an external payer withdrawal or cancellation API.

## Security and measurement

- The managed Model Armor measurement is available in
  [`evidence/model-armor-measurement.json`](../evidence/model-armor-measurement.json):
  seven synthetic scans completed with precision `1.0`, recall `0.75`, and
  false-positive rate `0.0`. It is a labeled provider probe; the hosted
  default boundary is separately verified in
  [`docs/audits/managed-security-cloud-run.md`](audits/managed-security-cloud-run.md).
- A separate serverless Gemma MaaS tripwire measurement is available in
  [`evidence/gemma-tripwire-measurement.json`](../evidence/gemma-tripwire-measurement.json):
  seven synthetic scans completed with precision `1.0`, recall `1.0`, and
  false-positive rate `0.0`, with zero provider errors or inconclusive scans.
  It is not a clinical decision. The hosted default boundary also cleared a
  fresh synthetic case through Model Armor followed by Gemma and quarantined a
  synthetic injection before denial parsing. The attempted temporary GPU deployment was rejected
  before resource creation because the selected region had zero L4 quota; no
  GPU endpoint remains. MaaS is serverless/pay-as-you-go, so there is no
  project endpoint or model resource to delete after the measurement.
- `make measure-local-security` measures the local deterministic fallback on
  synthetic labeled fixtures and writes aggregate counts only. Those results
  must not be described as Model Armor or Gemma measurements.
- The full adversarial suite and IAM assertion suite are not yet complete.
- The named-catch report, control arms, adjudication ablation, and failure
  distribution are not yet available.

These limitations are the current truth as of 2026-08-31. They should be
replaced by evidence-backed results only after the corresponding capability
has run successfully.
