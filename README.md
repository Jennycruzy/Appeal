# Appeal

**Appeal is an autonomous, policy-grounded operations fleet for recovering
health-insurance denials without surrendering clinical or mutation authority
to a model.** Seven specialized agents turn an untrusted denial into a
criterion-linked evidence package, pause for clinician authorization, submit
exactly once, and continue working when payer responses, new evidence, or
statutory deadlines arrive hours or weeks later.

[Open the clinician operations board](https://onyx-yeti-506606-i9.web.app) ·
[Inspect the architecture](docs/ARCHITECTURE.md) ·
[Follow the judge evidence map](docs/JUDGING.md) ·
[Read the evaluation protocol](docs/EVALUATION.md)

## Judge route

Appeal is easiest to evaluate in this order:

1. Open the clinician board and follow one case from intake to the approval
   boundary.
2. Read the [judge evidence map](docs/JUDGING.md) for the hosted control-plane
   proofs and their exact aggregate artifacts.
3. Inspect the [CMS evaluation rebuild](docs/CMS_LEGAL_GROUND_REVIEW.md): real
   regulator summaries are screened before sampling, official outcomes are
   scored separately, and legal-ground gold is gated on independent human
   review.
4. Trace the [architecture](docs/ARCHITECTURE.md) from untrusted intake,
   through policy/evidence controls, to the single mutation gate and durable
   payer wake.

The central design claim is precise: Gemini can analyze ambiguity, while
deterministic policy, evidence sufficiency, tenant scope, and clinician
authorization control authority.

## What is running

- An authenticated, tenant-scoped clinician board and signed mobile approval
  route on Firebase Hosting and Firebase Authentication.
- A durable Cloud Run workflow backed by Firestore, authenticated Pub/Sub
  continuation, and an OIDC-protected Cloud Scheduler deadline sentinel.
- A seven-role Google ADK graph on managed Agent Runtime with Agent Identity,
  Agent Registry, scoped Memory Bank state, and Cloud Trace telemetry.
- A fail-closed Agent Gateway and IAP policy that permits scoped evidence reads
  while denying a destructive canary before it reaches the tool service.
- Inline Model Armor and Gemma screening at untrusted input, model egress, and
  memory boundaries.
- A single idempotent Submission Gate, clinician veto, tamper-evident receipts,
  and a compensating-action journal.

## Proven operating outcomes

The deployed workflow has completed an authenticated payer-event wake from
Pub/Sub, resumed the matching Firestore session, reached `CLOSED_WON`, and
preserved exactly one external mutation under duplicate delivery. A hostile
instruction was quarantined before denial parsing with zero mutations. The
hosted clinician flow enforces Firebase tenant claims and a short-lived signed
mobile approval capability. These are live service and control-plane results,
not hard-coded UI states; the aggregate evidence is linked from
[the judging map](docs/JUDGING.md).

## Data and validation boundary

Appeal is production-shaped infrastructure. The hosted evaluation environment
uses composite cases and contains no PHI; the separate validation program uses
de-identified material and public regulator data. Production payer connectivity
and prospective clinical validation are still in progress, so Appeal does not
claim to have filed a real payer appeal. Public CMS QIC decision summaries
ground the regulator benchmark; complete case-level clinical efficacy remains
deliberately unclaimed until an authorized denial, policy, chart, filed appeal,
and outcome can be evaluated together.

## Evidence and validation status

The project has two separate real-data release tracks. The repository does
**not** claim a completed full-case Appeal evaluation.

1. The **regulator-outcome benchmark** measures against real regulator
   determinations and regulator-authored summary findings. Its authoritative
   acceptance record is
   [`evidence/cms-qic-decision-search.json`](evidence/cms-qic-decision-search.json).
2. The **full Appeal case corpus** requires the original denial, policy
   criteria, clinical evidence, internal appeal, external-review rationale,
   and final outcome in one de-identified case package. Its acquisition and
   acceptance boundary are recorded in
   [`docs/full-appeal-corpus-acquisition.md`](docs/full-appeal-corpus-acquisition.md)
   and [`evidence/full-appeal-case-corpus-acceptance.json`](evidence/full-appeal-case-corpus-acceptance.json).

The primary public source selected for the regulator-summary benchmark is now
the official CMS Qualified Independent Contractor (QIC) Decision Search API.
At the latest inspection it reported 901,471 Part C records and 240,958 Part D
records, with explicit `decision`, `appeal_type`, `decision_rationale`,
`coverage_rules`, condition, requested item/service or drug, and decision-date
fields. Its metadata, live counts, schema checks, and field policy are in
[`evidence/cms-qic-decision-search.json`](evidence/cms-qic-decision-search.json)
and the implementation boundary is in
[`docs/cms-qic-decision-benchmark.md`](docs/cms-qic-decision-benchmark.md).
This is a real regulator-authored decision-summary source and is not a full raw
clinical case package: the original denial letter, complete clinical evidence,
internal appeal, and original plan-policy version are not exposed in the API.
The project therefore accepts it for regulator-summary benchmarking while
keeping full-case Appeal evaluations at zero.

The active quality track is a separate, screened CMS legal-ground benchmark.
It resamples the accepted Part D population only after excluding empty
rationales, empty policy context, technical privacy candidates, and likely
professional names. The generated artifact has 188,102 eligible rows after
screening, with 150 sampled rows and a 50-row locked test. Its official CMS
`Decision` outcome remains hidden from review and is scored separately from
the inferred legal ground. The legal-ground locked set uses two blank,
independently ordered human-review sheets; assistant-proposed labels are not
eligible for gold. The [sample manifest](evidence/cms-qic-part-d-legal-ground-benchmark-v2.json),
[post-write audit](evidence/cms-qic-part-d-legal-ground-benchmark-v2-audit.json),
current [human-review status](evidence/cms-qic-legal-ground-annotation-status-v2.json),
and [track guide](docs/CMS_LEGAL_GROUND_REVIEW.md) make the boundary inspectable.

The repository's current evidence records the protocol and artifact hashes;
human gold and narrative-bearing queues remain outside Git until both reviews
are complete. The public status must therefore distinguish `official CMS
outcome scoring`, `inferred legal-ground scoring`, and `full Appeal evaluation`
instead of collapsing them into one accuracy number.

The dated official Part D bulk CSV was also preserved unchanged outside the
repository as a fallback inspection artifact. Its streaming inspection covered
240,958 rows and recorded the file hash in
[`evidence/cms-qic-part-d-bulk-inspection.json`](evidence/cms-qic-part-d-bulk-inspection.json).
The bulk headers map mechanically to the API fields but omit `record_number`,
and its technical scan found 453 hashed privacy candidate locators. The bulk
artifact is not accepted wholesale. Under the explicit workspace-owner
decision recorded in
[`evidence/cms-qic-part-d-bulk-acceptance.json`](evidence/cms-qic-part-d-bulk-acceptance.json),
all 192 `f` candidate groups are included and the 42 `b`/`l` groups are
excluded, removing 42 rows. The retained 240,916-row subset is accepted for
local regulator-summary evaluation only. The source-native `record_number`
remains absent; the manifest uses the pinned file SHA-256 plus row SHA-256 as
content identity and records occurrence disambiguation for duplicate rows.
The assistant-delegated proposal remains preserved outside the repository as
the decision input; no raw values are committed.

The official DMHC download and API are currently returning Cloudflare 403
responses, so DMHC remains a secondary candidate rather than the current
benchmark source.
A public Kaggle mirror was therefore downloaded outside the repository and
inspected as a fallback candidate: 19,245 rows, 11 columns, `Determination`,
`Findings`, treatment categories, and `Reference ID`. It has no explicit
`Denial Reason` field and its technical scan found 22 physical-address-shaped
values. It is a candidate for the regulator-outcome track only and remains
pending provenance, privacy, reuse, and prior-authorization review. The
metadata-only record is
[`evidence/dmhc-kaggle-acquisition.json`](evidence/dmhc-kaggle-acquisition.json).

Two other manually acquired regulator candidates are also tracked locally:

- The NY DFS all-years export is preserved unchanged and local-only.
- It contains 61,606 observed rows, an `Appeal Decision` outcome, and a
  `Denial Reason` column.
- The archive UI exposes an `Appeal Type` filter, but the export has no
  `Appeal Type` column. That mapping is unresolved and is not inferred.
- Oregon's official IRO Case Detail Report is also preserved unchanged and
  local-only. It contains 2,230 observed case rows, an explicit `Case Outcome`,
  review type/category fields, and a treatment field. The project owner has
  authorized local-only use of all 1,640 completed-review outcome rows based on
  the official public download; no redistribution or prior-authorization claim
  is made.
- NY privacy/mapping/reuse review remains unresolved. Oregon is accepted only
  for local external-review outcome evaluation. The fail-closed adapter
  preflight has run across all 1,640 accepted rows and abstained before denial
  parsing because the source does not provide denial text, policy references,
  or clinical evidence. Full Appeal evaluations and regulator-ground-truth
  comparisons remain **zero**.
- A published DMHC case example is a discovery lead only; it is not an official
  payload import, accepted corpus row, or evaluation result. California DWC was
  investigated separately and rejected as a primary benchmark because it is a
  workers' compensation source and its public index does not provide the
  complete denial packet needed here.

Start with the [CMS QIC benchmark record](docs/cms-qic-decision-benchmark.md),
the [real-denial smart acquisition path](docs/real-denial-smart-path.md), the
[NY acceptance manifest](evidence/ny-dfs-acceptance.json), the [Oregon
acceptance manifest](evidence/oregon-acceptance.json), and the review-request
record for [NY DFS](docs/ny-dfs-review-request.md) plus the optional Oregon
follow-up [request](docs/oregon-iro-review-request.md). The active full-scope
execution plan is maintained locally and is intentionally not part of the
public repository.

## What is and is not evidence

The Synthea/HAPI material is a reproducible integration fixture and data-plane
check. It is not real-denial evidence and does not support a clinical or
regulator-ground-truth claim. The CMS QIC API is the accepted public source for
regulator-authored decision-summary benchmarking; it does not supply the
clinical Evidence Floor required for a full Appeal run. The Oregon source-specific gate permits a
local-only adapter preflight and outcome-label inventory; it does not yet
support a full denial appeal evaluation. The NY source remains separately
blocked.

All corpus gates are fail-closed within their respective tracks. CMS API rows,
the raw NY DFS and Oregon files, and the DMHC mirror
are not committed. The local Oregon evaluation input and DMHC mirror CSV stay
outside the repository; repository evidence contains metadata and aggregate
counts only—not case numbers, treatment strings, or narrative values. The CMS
inspectors likewise write no source row values. The bulk fallback has a
terminal-only reviewer for its technical candidates; for this pinned local
subset, the explicit owner policy is recorded in the bulk acceptance manifest
and its decision input stays outside the repository.

## Google Cloud status

The deterministic Appeal HTTP backend is deployed to Cloud Run in project
`onyx-yeti-506606-i9` (display name `Appeal`), region `europe-west2`; the
latest ready revision is `appeal-backend-00028-cgz` with 100% traffic. The
verified service URL is
<https://appeal-backend-hhcjpefk2q-nw.a.run.app>. Its `/api/healthz` endpoint
returns `status: ok` with `storage: firestore`, `event_spine: pubsub_firestore`,
`security: managed_model_armor_gemma`, and an allowlisted managed-runtime
checkpoint. A controlled case passed the managed Model Armor -> Gemma boundary
on inbound, egress, and memory surfaces, then completed clinician approval, one
submission mutation, and payer adjudication to `CLOSED_WON`. A hostile-input
case was blocked at inbound and entered `QUARANTINED` before denial parsing,
with zero external mutations. The board returns persisted cases from
Firestore.
The aggregate deployment record is
[`evidence/cloud-run-deployment.json`](evidence/cloud-run-deployment.json),
with the persistence audit in
[`docs/audits/cloud-persistence.md`](docs/audits/cloud-persistence.md).
The current clinician-review deployment check is recorded in
[`evidence/clinician-review-deployment.json`](evidence/clinician-review-deployment.json).
The hosted payer wake artifact is the authoritative end-to-end Pub/Sub trace
on revision `appeal-backend-00026-42q`: the authenticated reference-only payer
event resumed the Firestore session to `CLOSED_WON`, preserved one external
mutation, and remained idempotent on duplicate delivery. The implementation
also writes case state and its resumable session atomically, so concurrent
delivery cannot leave a stale session fingerprint.
The managed-security audit is
[`docs/audits/managed-security-cloud-run.md`](docs/audits/managed-security-cloud-run.md).
The Pub/Sub audit is
[`docs/audits/pubsub-event-spine.md`](docs/audits/pubsub-event-spine.md).

The hosted service is a synthetic-only demonstration endpoint with no real
case data uploaded. Firestore persists the immutable case state, safe
references, a reference-only workflow session, and a hash-chained receipt
ledger. A synthetic case created on revision `00012`, approved after revision
`00013` replaced it, and adjudicated after revision `00014` replaced it again;
the final state was `CLOSED_WON` with one external mutation. It proves the
Google Cloud backend deployment, restart-safe workflow boundary, Firestore
write path, hosted Model Armor/Gemma boundary, and managed Pub/Sub event
delivery. A separate managed Agent Runtime deployment now hosts the same
seven-role ADK graph with Agent Identity and Agent Registry metadata; its
synthetic query, managed-session creation, and reference-only Memory Bank
write are recorded separately. The current revision also invokes that managed
graph once for an allowlisted synthetic `intake/clear` checkpoint, with
Firestore idempotency and aggregate-only query evidence; the checkpoint record
is [`evidence/agent-runtime-subscriber.json`](evidence/agent-runtime-subscriber.json).
The existing synthetic Memory Bank record now has a verified readback, and
Cloud Trace contains two matching Agent Runtime traces in the verification
window. Managed Runtime egress is now bound to a regional Agent Gateway with
an enforced, fail-closed IAP policy; the observed platform destinations are
registered and endpoint-specific egress permissions are verified. A routed
MCP read was allowed by the Gateway and a destructive canary was denied with
HTTP 403 before Cloud Run, with zero mutation; the aggregate proof is
[`evidence/agent-gateway-mcp-enforcement.json`](evidence/agent-gateway-mcp-enforcement.json).
The hosted payer wake is now verified separately: a synthetic typed
`payer.determination.received` event arrived through the authenticated Pub/Sub
push, resumed the Firestore session, closed the case, and preserved exactly one
mutation; replaying the same event ID returned HTTP 200 without another
mutation. The aggregate trace is
[`evidence/cloud-run-async-workflow.json`](evidence/cloud-run-async-workflow.json),
with the audit in
[`docs/audits/hosted-async-workflow.md`](docs/audits/hosted-async-workflow.md).
The payer determination boundary is also deployed as a separate private Cloud
Run service under its own service account. It accepts bounded evidence
references only, returns no mutation authority, and rejects unauthenticated
requests; its authenticated synthetic probe is recorded in
[`evidence/payer-service.json`](evidence/payer-service.json), with the contract
audit in [`docs/audits/payer-service.md`](docs/audits/payer-service.md).
The managed Agent Runtime remains advisory and synthetic-only; a later
checkpoint may be recorded as failed/retryable when Vertex shared capacity is
exhausted, without redelivering the durable workflow event. Firebase is now
linked to the active project. Auth is initialized with Email/Password enabled,
one synthetic clinician account carries the `tenant-demo-hosted` claim, and
the Firebase Hosting dashboard and mobile approval page are live at
<https://onyx-yeti-506606-i9.web.app>. Cloud Run revision `00027-zm5` enforces
the Firebase ID-token/tenant boundary and reads the signing secret from Secret
Manager. The hosted six-case board proof and remaining browser/video gates are
recorded in [`evidence/firebase-auth-boundary.json`](evidence/firebase-auth-boundary.json).
The governance audit is
[`docs/audits/agent-gateway.md`](docs/audits/agent-gateway.md), with aggregate
evidence in
[`evidence/agent-gateway-governance.json`](evidence/agent-gateway-governance.json).
The current cloud evidence is in the [Agent Gateway audit](docs/audits/agent-gateway.md)
and the [aggregate governance record](evidence/agent-gateway-governance.json).

The Deadline Sentinel is also scheduled on Cloud Scheduler job
`appeal-deadline-sentinel` at the top of every UTC hour. Its OIDC identity is
checked by the Sentinel route; an anonymous request returned `401`, while a
real Scheduler invocation returned `200` and closed two synthetic expired
cases. The scheduler and seed evidence are included in
[`evidence/cloud-run-deployment.json`](evidence/cloud-run-deployment.json) and
[`docs/audits/deadline-sentinel.md`](docs/audits/deadline-sentinel.md).

## Local product path

The repository now contains a runnable local seven-role workflow around the
deterministic Appeal core. It includes Intake, Denial Parser, Policy Analyst,
Evidence Miner, Argument Builder, Deadline Sentinel, and Escalation Strategist,
plus the four-veto combinator, quarantine state, Evidence Floor, clinician
co-signature, single-mutation submission gate, statutory clock, and hash-chained
receipts. The local platform runtime adds reference-only event delivery,
tenant/case-scoped memory, an independent payer adjudicator, and a
compensating-action journal. The same policy-controlled workflow service is
deployed to Cloud Run as the hosted reference implementation. The hosted workflow includes
the managed Model Armor -> Gemma boundary and a Firestore-registered Pub/Sub
event spine. The seven-role ADK graph is also deployed to managed Agent
Runtime, with Agent Registry and Agent Identity metadata plus session and Memory
Bank write probes. The Cloud Run service and managed Agent
Runtime deployment remain separate boundaries; the authenticated Pub/Sub
subscriber now invokes the managed runtime only for one allowlisted
checkpoint, while the broader workflow remains deterministic and in-process.
The routed MCP governance probe is enforced and fail-closed, but it is a
control-plane proof rather than proof of the full subscriber-driven appeal
workflow. A later advisory smoke may still hit Vertex shared-capacity quota;
that does not weaken the Gateway denial.
The scoring handoff is deferred until this workflow is complete; completed
full Appeal evaluations remain zero.

Run the local vertical slice with:

```text
make run-local-workflow
```

The control-plane boundaries are mapped in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

The judge-facing evidence map is in
[`docs/JUDGING.md`](docs/JUDGING.md). It separates hosted proofs, local
restart/utility proofs, real regulator-summary data, and capabilities that are
still open.

Run the local platform runtime, including a synthetic payer determination,
with:

```text
make run-local-runtime
```

The service lifecycle is also covered by tests as separate open, clinician
approval, and payer-determination operations. The deployed Cloud Run demo uses
Firestore for case metadata, reference-only workflow sessions, and receipts;
the service remains synthetic-only and unauthenticated.

Exercise the restart-safe asynchronous path with:

```text
make run-async-workflow-proof
```

This local, aggregate-only harness covers a missing-evidence wake, a payer
determination after restart, a protected deadline tick, receipt-chain
verification, patient-scope binding, and duplicate-event handling. Its report
is [`evidence/async-workflow-proof.json`](evidence/async-workflow-proof.json).
It is not a claim that the current hosted Cloud Run revision runs the complete
workflow; the hosted subscriber remains a bounded synthetic checkpoint.

Measure the local operational utility and control scenarios with:

```text
make measure-operational-utility
```

The aggregate report is
[`evidence/operational-utility-measurement.json`](evidence/operational-utility-measurement.json),
with its honest interpretation and dollar-claim boundary in
[`docs/audits/operational-utility.md`](docs/audits/operational-utility.md).

Seed the six local judge stories (clean, quarantine, abstention, evidence
wake, missed deadline, and level-two escalation) with:

```text
make seed-demo-cases
```

The aggregate board manifest is
[`evidence/seeded-demo-tenant.json`](evidence/seeded-demo-tenant.json). It is
local synthetic evidence; the hosted six-case board is separately recorded in
[`evidence/firebase-auth-boundary.json`](evidence/firebase-auth-boundary.json).
The hosted payer continuation proof is separate from the board, and the
fail-closed Firebase/tenant verifier and signed mobile-link contract are now
deployed as described in
[`docs/audits/auth-dashboard-contract.md`](docs/audits/auth-dashboard-contract.md).

Run the synthetic Stage B case through the real ADK `Runner` and Gemini vision
path with:

```text
make run-adk-case
```

The ref-only exit artifact is
`evidence/adk-stage-b-case-exit.json`, with the audit narrative in
[`docs/audits/stage-b-adk-exit.md`](docs/audits/stage-b-adk-exit.md). The
case is synthetic and the Cloud Run service remains a deterministic facade;
this particular run does not claim a full Appeal evaluation. The separate
managed Agent Runtime deployment is recorded in
[`docs/audits/agent-runtime.md`](docs/audits/agent-runtime.md).

For local HTTP integration testing only, run:

```text
make run-local-api
```

It binds to loopback and exposes `/healthz` (and `/api/healthz` for Cloud Run),
`POST /api/demo/cases`,
`GET /api/cases/tenant-demo`, and the approval/adjudication routes. It is not
authenticated or suitable for public use.

Measure the local deterministic security fallback with:

```text
make measure-local-security
```

Measure the configured managed Model Armor template with:

```text
make measure-model-armor
```

That report contains aggregate counts only and is recorded in
`evidence/model-armor-measurement.json`. Measure the separate serverless Gemma
tripwire probe with:

```text
make measure-gemma
```

Its seven synthetic scans are recorded in
`evidence/gemma-tripwire-measurement.json` as aggregate counts only. This is a
provider measurement and not a clinical decision; the hosted default boundary
also exercised Model Armor followed by Gemma on a fresh synthetic case. The
temporary GPU deployment path was rejected by zero regional
quota before creating an endpoint; the measurement therefore uses Google's
serverless Gemma MaaS route and leaves no GPU resource to delete.

The default local metadata report and JSONL receipt ledger are written outside
the repository under `../Downloads/`. The Cloud Run deployment uses its
Firestore receipt adapter instead. Add `--approve` to simulate the clinician
co-signature, `--inject` to exercise quarantine, or `--missing-evidence` to
exercise fail-closed abstention by invoking
`scripts/run_local_workflow.py` directly.

## Verification

```text
make test
make typecheck
make run-async-workflow-proof
make measure-operational-utility
make validate-ny-dfs
APPEAL_CMS_QIC_ACA='<public ACA value>' make inspect-cms-qic
make run-cms-qic-summary \
  CMS_QIC_LOCAL_OUTPUT=../Downloads/cms-qic-part-d-summary.jsonl \
  CMS_QIC_LOCAL_MANIFEST=../Downloads/cms-qic-part-d-summary.manifest.json
make scan-cms-qic-privacy \
  CMS_QIC_PART=part_d \
  CMS_QIC_PRIVACY_SCAN_REPORT=evidence/cms-qic-part-d-privacy-scan.json
make inspect-cms-qic-bulk \
  CMS_QIC_BULK_INPUT=../Downloads/cms-qic-partd-2026-08-25.csv \
  CMS_QIC_BULK_SOURCE_ETAG='<captured official ETag>' \
  CMS_QIC_BULK_REPORT=evidence/cms-qic-part-d-bulk-inspection.json
make review-cms-qic-bulk \
  CMS_QIC_BULK_INPUT=../Downloads/cms-qic-partd-2026-08-25.csv \
  CMS_QIC_BULK_REPORT=evidence/cms-qic-part-d-bulk-inspection.json \
  CMS_QIC_BULK_PRIVACY_DECISIONS=../Downloads/cms-qic-partd-privacy-decisions.json
make propose-cms-qic-bulk \
  CMS_QIC_BULK_INPUT=../Downloads/cms-qic-partd-2026-08-25.csv \
  CMS_QIC_BULK_REPORT=evidence/cms-qic-part-d-bulk-inspection.json \
  CMS_QIC_BULK_PRIVACY_PROPOSAL=../Downloads/cms-qic-partd-privacy-decisions-agent-proposed.json
make accept-cms-qic-bulk \
  CMS_QIC_BULK_INPUT=../Downloads/cms-qic-partd-2026-08-25.csv \
  CMS_QIC_BULK_REPORT=evidence/cms-qic-part-d-bulk-inspection.json \
  CMS_QIC_BULK_PRIVACY_PROPOSAL=../Downloads/cms-qic-partd-privacy-decisions-agent-proposed.json \
  CMS_QIC_BULK_ACCEPTANCE_MANIFEST=evidence/cms-qic-part-d-bulk-acceptance.json
make inspect-dmhc-imr \
  DMHC_IMR_INPUT=../Downloads/independent-medical-review-determinations-trends.csv
make inspect-oregon-iro \
  OREGON_IRO_INPUT=../Downloads/oregon-iro-case-detail-report.xlsx
make prepare-oregon-local-evaluation \
  OREGON_IRO_INPUT=../Downloads/oregon-iro-case-detail-report.xlsx \
  OREGON_IRO_LOCAL_OUTPUT=../Downloads/oregon-iro-local-evaluation.json
make run-oregon-local-evaluation \
  OREGON_IRO_LOCAL_OUTPUT=../Downloads/oregon-iro-local-evaluation.json
```

The proposal command is a conservative technical triage aid. The current
acceptance manifest records the explicit owner policy to include all `f`
groups and exclude all `b`/`l` groups; the 42 excluded rows are not individually
reviewed.

The Oregon run writes aggregate-only evidence to
`evidence/oregon-evaluation.json`. Its current result is an adapter preflight
with 1,640 explicit abstentions, not an Appeal score.

To create the local privacy-review packet, use the unchanged workbook and an
output path outside this repository:

```text
make prepare-ny-dfs-review \
  NY_DFS_INPUT=../Downloads/peasadata.xlsx \
  NY_DFS_PRIVACY_REVIEW=../Downloads/ny-dfs-privacy-review.json
```

Then run `make review-ny-dfs-privacy`. The reviewer sees candidate values only
in the terminal; the saved decision file contains hashes and decisions only.
Hash that decision file and record the hash in the acceptance manifest after
the review is complete.
