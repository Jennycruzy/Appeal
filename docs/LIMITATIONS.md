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
- Cloud Run, Agent Runtime, Agent Registry, Agent Identity, managed Memory
  Bank, Agent Gateway, Agent Policies, and Cloud Observability are not yet
  deployed from this repository. A managed Model Armor template has been
  configured and measured separately; it is not yet the default workflow
  boundary. Local fallback seams for event delivery, case storage, scoped
  memory, payer adjudication, and reversibility are present under
  `src/appeal_platform/`.
- The 2026-08-28 probe found an attached authorized-user ADC credential. It
  refreshed successfully and passed a read-only Resource Manager check for
  project `appeal-fleet-2026-0825` (`APPEAL Fleet 2026`, ACTIVE); the same
  credential also passed a read-only check for the documented target
  `onyx-yeti-506606-i9` (`My Project 27960`, ACTIVE). The active `gcloud` CLI
  profile still has no selected account, although its project is set to the
  documented target. The project `.venv` contains ADK; the system Python
  interpreter does not. This proves credential/project access, not a managed
  deployment or a completed ADK case run.
- The current local seven-agent implementation demonstrates the role
  boundaries and governance contracts; it is not represented as a managed
  cloud deployment or a complete Gemini-backed appeal case evaluation.

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

- The local workflow does not yet provide a production case API, web console,
  Firebase authentication, Cloud Scheduler, managed Pub/Sub, or persistent
  multi-tenant storage. The local runtime is process-local and intentionally
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
- A Gemma tripwire measurement is not yet available. Direct publisher
  inference was unavailable, and serving Gemma requires a Vertex endpoint;
  the smallest checked option uses a billable GPU. Deployment and ongoing
  cost therefore remain pending explicit authorization.
- `make measure-local-security` measures the local deterministic fallback on
  synthetic labeled fixtures and writes aggregate counts only. Those results
  must not be described as Model Armor or Gemma measurements.
- The full adversarial suite and IAM assertion suite are not yet complete.
- The named-catch report, control arms, adjudication ablation, and failure
  distribution are not yet available.

These limitations are the current truth as of 2026-08-28. They should be
replaced by evidence-backed results only after the corresponding capability
has run successfully.
