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
  `appeal-backend-00002-d24`. Its health endpoint and one synthetic case
  lifecycle were verified; the aggregate record is
  [`evidence/cloud-run-deployment.json`](../evidence/cloud-run-deployment.json).
  The service is unauthenticated and process-local, accepts no real case data,
  and is not a production API.
- Agent Runtime, Agent Registry, Agent Identity, managed Memory Bank, Agent
  Gateway, Agent Policies, Firebase Auth, Firestore, Pub/Sub, and managed Cloud
  Observability are not yet deployed from this repository. A managed Model
  Armor template has been configured and measured separately; it is not yet
  the default workflow boundary. Local fallback seams for event delivery,
  case storage, scoped memory, payer adjudication, and reversibility are
  present under `src/appeal_platform/`.
- The current seven-agent implementation demonstrates the role boundaries and
  governance contracts. The ADK/Gemini smoke ran separately in the project
  environment; the deployed Cloud Run container exposes the deterministic API
  facade, not a complete Gemini-backed appeal case evaluation.

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

- The repository does not yet provide a web console, Firebase authentication,
  Cloud Scheduler, managed Pub/Sub, or persistent multi-tenant storage. The
  Cloud Run HTTP facade is synthetic-only and process-local; it is intentionally
  not a production deployment.
- The local event spine records and deduplicates workflow events, but the
  deterministic workflow still invokes role adapters in-process; subscriber-
  driven agent execution is not yet implemented.
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
  false-positive rate `0.0`. It is a separate provider probe and is not yet
  the default workflow boundary.
- A separate serverless Gemma MaaS tripwire measurement is available in
  [`evidence/gemma-tripwire-measurement.json`](../evidence/gemma-tripwire-measurement.json):
  seven synthetic scans completed with precision `1.0`, recall `1.0`, and
  false-positive rate `0.0`, with zero provider errors or inconclusive scans.
  It is not yet wired into the default workflow boundary and is not a
  clinical decision. The attempted temporary GPU deployment was rejected
  before resource creation because the selected region had zero L4 quota; no
  GPU endpoint remains. MaaS is serverless/pay-as-you-go, so there is no
  project endpoint or model resource to delete after the measurement.
- `make measure-local-security` measures the local deterministic fallback on
  synthetic labeled fixtures and writes aggregate counts only. Those results
  must not be described as Model Armor or Gemma measurements.
- The full adversarial suite and IAM assertion suite are not yet complete.
- The named-catch report, control arms, adjudication ablation, and failure
  distribution are not yet available.

These limitations are the current truth as of 2026-08-28. They should be
replaced by evidence-backed results only after the corresponding capability
has run successfully.
