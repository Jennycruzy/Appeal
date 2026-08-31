# Judge-facing evidence map

Recorded: 2026-08-31

This page is the shortest honest route through the project. It separates
verified hosted boundaries from deterministic local proofs and from work that
is still unverified. Every number below should be checked against the linked
aggregate artifact; no raw clinical content or patient identifier is required
to reproduce the local proofs.

## Current status

| Area | Status | What a reviewer can verify now |
|---|---|---|
| Core controls | Verified locally | Evidence Floor, four-veto combinator, quarantine, human approval, single mutation representation, deadlines, receipts, and compensation |
| Registry and Gateway | Verified hosted | Seven Agent Registry records, scoped MCP read, denied mutation canary, enforced fail-closed Gateway, zero mutation |
| Durable asynchronous workflow | Verified hosted and locally | Hosted authenticated Pub/Sub payer wake, Firestore resume, duplicate delivery, one mutation; local evidence wake/deadline/restart proof |
| ADK/Gemini | Provider and managed-runtime smoke verified; full hosted workflow open | Seven-role synthetic ADK run and one managed subscriber checkpoint; no full case path claim |
| Payer and mutation | Verified hosted boundary; real payer integration open | Private payer Cloud Run service with dedicated identity, bounded determination contract, typed async wake, one gated synthetic mutation and compensation journal |
| Auth, dashboard, mobile clinician loop | Hosted synthetic proof | Firebase Email/Password Auth, a `tenant_id` claim, the Hosting board/mobile pages, and a fail-closed Cloud Run boundary are live; browser/mobile capture remains in the final video gate |
| Real-data evaluation | CMS outcome track is explicit; legal-ground track is screened and human-gold gated | The active CMS legal-ground sample is audited before review; official `Decision` scoring and inferred legal-ground scoring use separate denominators. Completed full Appeal evaluations remain zero |
| Utility | Local sensitivity measurement | Six aggregate synthetic scenarios, published burden references, and an explicitly null recoverable-dollar amount |

## Requirement-to-proof map

| Judge requirement | Exact proof route | Evidence / limitation |
|---|---|---|
| Untrusted intake is screened before parsing | `make measure-local-security`; hosted clean/injection smoke | [`evidence/model-armor-measurement.json`](../evidence/model-armor-measurement.json), [`docs/audits/managed-security-cloud-run.md`](audits/managed-security-cloud-run.md). Provider measurements are synthetic and not clinical evaluation. |
| Agents have declared capabilities | `GET /api/agents/{role}` on the local/Cloud Run API | [`evidence/agent-runtime-deployment.json`](../evidence/agent-runtime-deployment.json), [`docs/audits/agent-registry.md`](audits/agent-registry.md). The live registry records are hosted proof; the API facade itself is not an auth boundary. |
| Scoped chart read and mutation denial | Managed Runtime marker-gated governance probe | [`evidence/agent-gateway-mcp-enforcement.json`](../evidence/agent-gateway-mcp-enforcement.json), [`docs/audits/agent-gateway.md`](audits/agent-gateway.md). The canary never executes a real mutation; the real Submission Gate tool is intentionally undiscoverable. |
| Case survives restart and external wakes it | Hosted synthetic payer event plus `make run-async-workflow-proof` | [`evidence/cloud-run-async-workflow.json`](../evidence/cloud-run-async-workflow.json), [`docs/audits/hosted-async-workflow.md`](audits/hosted-async-workflow.md), and [`evidence/async-workflow-proof.json`](../evidence/async-workflow-proof.json). The hosted proof covers payer continuation; the local harness covers evidence wake and deadline replay. |
| Deadline wake is protected and idempotent | `POST /api/sentinel/tick` with Scheduler identity; local sentinel test | [`docs/audits/deadline-sentinel.md`](audits/deadline-sentinel.md), [`evidence/cloud-run-deployment.json`](../evidence/cloud-run-deployment.json). Hosted Scheduler proof exists; local session continuity is covered by `test_deadline_sentinel_updates_a_persisted_session_capsule`. |
| Model path and multimodal input | `make run-adk-case`; managed Runtime smoke | [`evidence/adk-stage-b-case-exit.json`](../evidence/adk-stage-b-case-exit.json), [`evidence/agent-runtime-deployment.json`](../evidence/agent-runtime-deployment.json). These are provider/runtime proofs, not a complete hosted Appeal evaluation. A later advisory smoke may still hit shared Vertex capacity; that does not weaken Gateway denial. |
| Payer determination cannot mutate directly | Private payer Cloud Run service plus hosted typed payer event | [`evidence/payer-service.json`](../evidence/payer-service.json), [`docs/audits/payer-service.md`](audits/payer-service.md), [`evidence/cloud-run-async-workflow.json`](../evidence/cloud-run-async-workflow.json), and tests in [`tests/test_payer_service.py`](../tests/test_payer_service.py). The service is synthetic-only; no real payer API is connected. |
| Exactly one gated mutation and compensation | `make run-async-workflow-proof`; `PayerAdjudicator` path | [`evidence/async-workflow-proof.json`](../evidence/async-workflow-proof.json), [`src/appeal_platform/reversibility.py`](../src/appeal_platform/reversibility.py). The external reference is synthetic; no payer API is called. |
| Real-data grounding | CMS QIC summary and Oregon outcome adapters | [`evidence/cms-qic-decision-search.json`](../evidence/cms-qic-decision-search.json), [`evidence/oregon-evaluation.json`](../evidence/oregon-evaluation.json), [`docs/DATA_PROVENANCE.md`](DATA_PROVENANCE.md). These sources do not contain the complete denial, policy, chart, appeal, and outcome package needed for a full-case score. |
| Legal-ground quality | Screened CMS Part D sample with independent human review contract | [`config/cms_part_d_legal_ground_taxonomy_v2.json`](../config/cms_part_d_legal_ground_taxonomy_v2.json), [`docs/CMS_LEGAL_GROUND_REVIEW.md`](CMS_LEGAL_GROUND_REVIEW.md), [`evidence/cms-qic-part-d-legal-ground-benchmark-v2.json`](../evidence/cms-qic-part-d-legal-ground-benchmark-v2.json), [`evidence/cms-qic-part-d-legal-ground-benchmark-v2-audit.json`](../evidence/cms-qic-part-d-legal-ground-benchmark-v2-audit.json), and current [`evidence/cms-qic-legal-ground-annotation-status-v2.json`](../evidence/cms-qic-legal-ground-annotation-status-v2.json). The gold score remains pending until two direct human reviews are imported. |
| Operational utility and controls | `make measure-operational-utility` | [`evidence/operational-utility-measurement.json`](../evidence/operational-utility-measurement.json), [`docs/audits/operational-utility.md`](audits/operational-utility.md). Metrics are aggregate synthetic workflow measures; the Oregon rate is an external-review proxy, and recoverable dollars are sensitivity-only. |
| Six seeded operating stories | `make seed-demo-cases` plus hosted board | [`evidence/seeded-demo-tenant.json`](../evidence/seeded-demo-tenant.json) records the local stories; [`evidence/firebase-auth-boundary.json`](../evidence/firebase-auth-boundary.json) records six hosted synthetic states and the live tenant board. |
| Receipts and observability | Local receipt verification; hosted Cloud Trace/Firestore audits | [`docs/audits/cloud-persistence.md`](audits/cloud-persistence.md), [`evidence/cloud-run-deployment.json`](../evidence/cloud-run-deployment.json). A complete hosted case trace across all roles is not yet captured. |
| Authenticated console and mobile approval | Hosted boundary verified | Firebase Auth/Email-Password, tenant claim enforcement, Hosting dashboard/mobile page, and Secret Manager-backed signed links are live. Use only the synthetic account and cases in [`evidence/firebase-auth-boundary.json`](../evidence/firebase-auth-boundary.json); no real-data workflow is claimed. |

## Reproduce the local proof package

```text
make test
make typecheck
make run-async-workflow-proof
make measure-operational-utility
git diff --check
```

The two proof commands write only aggregate JSON under `evidence/`; the
hash-chained receipt ledgers are written outside the repository under
`../Downloads/`. The local commands use deterministic synthetic fixtures and
do not prove clinical quality, payer agreement, or production throughput.

## Claims deliberately withheld

- No full Appeal evaluation is reported. A regulator summary is not a denial
  packet, and an external-review outcome is not a prior-authorization ground
  truth label.
- No PHI is uploaded, and no real payer submission or withdrawal occurs.
- Hosted Firebase-authenticated dashboard and the signed mobile clinician
  approval route are deployed and exercised at the boundary level with
  synthetic data. A full browser/mobile recording is still a submission gate,
  and the separate payer service remains synthetic-only with no real payer API.
- The utility report does not invent a dollar amount. Supply an authorized
  allowed amount before applying its sensitivity formula.
- A Vertex `_ResourceExhaustedError` is a quota/capacity failure in a later
  advisory smoke, not evidence that authentication is missing and not a
  bypass of the enforced Gateway policy.

The final video and public submission links are not recorded yet. Once made,
they should be added here with timestamps that point to the same routes and
artifacts rather than to staged screenshots.
