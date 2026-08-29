# Appeal

Appeal is a policy-grounded denial-appeal workflow with explicit evidence,
human-signature, deadline, and audit controls.

## Reviewer status

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

Start with the [release-track handoff](docs/HANDOFF.md#release-tracks-2026-08-28),
the [CMS QIC benchmark record](docs/cms-qic-decision-benchmark.md),
and the [real-denial smart acquisition path](docs/real-denial-smart-path.md),
then the [NY DFS handoff](docs/HANDOFF.md#ny-dfs-schema-mismatch--resume-here),
the [Oregon fallback](docs/HANDOFF.md#oregon-iro-case-detail-fallback), the
[NY acceptance manifest](evidence/ny-dfs-acceptance.json), the [Oregon
acceptance manifest](evidence/oregon-acceptance.json), and the review-request
record for [NY DFS](docs/ny-dfs-review-request.md) plus the optional Oregon
follow-up [request](docs/oregon-iro-review-request.md).

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
`onyx-yeti-506606-i9` (display name `Appeal`), region `europe-west2`, revision
`appeal-backend-00014-95f`, with 100% traffic on that revision. The verified
service URL is
<https://appeal-backend-hhcjpefk2q-nw.a.run.app>. Its `/api/healthz` endpoint
returned `status: ok` with `storage: firestore` and
`security: managed_model_armor_gemma`. A fresh synthetic case passed the
managed Model Armor -> Gemma boundary on inbound, egress, and memory surfaces,
then completed clinician approval, one submission mutation, and payer
adjudication to `CLOSED_WON`. A synthetic injection was blocked at inbound
and entered `QUARANTINED` before denial parsing, with zero external
mutations. The board then returned persisted synthetic cases from Firestore.
The aggregate deployment record is
[`evidence/cloud-run-deployment.json`](evidence/cloud-run-deployment.json),
with the persistence audit in
[`docs/audits/cloud-persistence.md`](docs/audits/cloud-persistence.md).
The managed-security audit is
[`docs/audits/managed-security-cloud-run.md`](docs/audits/managed-security-cloud-run.md).

This is a synthetic-only, unauthenticated demonstration endpoint with
no real case data uploaded. Firestore persists the immutable case state, safe
references, a reference-only workflow session, and a hash-chained receipt
ledger. A synthetic case created on revision `00012`, approved after revision
`00013` replaced it, and adjudicated after revision `00014` replaced it again;
the final state was `CLOSED_WON` with one external mutation. It proves the
Google Cloud backend deployment, restart-safe workflow boundary, Firestore
write path, and hosted Model Armor/Gemma boundary. It does not claim that the
managed Agent Runtime, Pub/Sub, or Firebase Auth is deployed.
See the [cloud handoff](docs/HANDOFF.md#google-cloud-hosting-status).

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
compensating-action journal. The same deterministic HTTP facade is deployed
for the synthetic Cloud Run demonstration. The hosted workflow now includes
the managed Model Armor -> Gemma boundary, while the ADK/Gemini smoke remains
separate provider evidence and the container is not yet a managed Agent
Runtime workflow. The scoring handoff is deferred until this workflow is
complete; completed full Appeal evaluations remain zero.

Run the synthetic vertical slice with:

```text
make run-local-workflow
```

The control-plane boundaries are mapped in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

Run the local platform runtime, including a synthetic payer determination,
with:

```text
make run-local-runtime
```

The service lifecycle is also covered by tests as separate open, clinician
approval, and payer-determination operations. The deployed Cloud Run demo uses
Firestore for case metadata, reference-only workflow sessions, and receipts;
the service remains synthetic-only and unauthenticated.

Run the synthetic Stage B case through the real ADK `Runner` and Gemini vision
path with:

```text
make run-adk-case
```

The ref-only exit artifact is
`evidence/adk-stage-b-case-exit.json`, with the audit narrative in
[`docs/audits/stage-b-adk-exit.md`](docs/audits/stage-b-adk-exit.md). The
case is synthetic and the Cloud Run service remains a deterministic facade;
this run does not claim a managed Agent Runtime deployment or a full Appeal
evaluation.

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
