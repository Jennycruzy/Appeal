# APPEAL build handoff

Updated: 2026-08-29

## Current state

The repository is on `main`, and the GitHub remote is configured as
`https://github.com/Jennycruzy/Appeal.git`. The existing commits have been
pushed to `origin/main`. The current Appeal project registration is
`onyx-yeti-506606-i9` (project number `835653516606`), selected from the
same-account Cloud Console evidence and recorded as the default in
`config/requirements.json`. The former `appeal-fleet-2026-0825` project is no
longer the target.

The cloud setup gate has moved past the initial billing/API blocker. The
2026-08-27 AI Studio console evidence shows a successful $10 Cloud Prepay
payment, Gemini API Paid Tier activation, and setup completion for the linked
account. The Google Cloud console also shows the active project's $300 free
trial with $0 used and 90 days remaining, but that is a separate Cloud trial
balance. Google's current [Gemini API billing guidance](https://ai.google.dev/gemini-api/docs/billing)
says Cloud Welcome/free-trial credits should not be assumed usable for Gemini
API or AI Studio usage. The private Prepay transaction or balance is not
exposed by this repository's metadata-only preflight, so the console's
Billing/Transactions view remains the authoritative confirmation of the
payment landing.

The live preflight confirmed `aiplatform.googleapis.com` is enabled for
`onyx-yeti-506606-i9`. Its regional custom-model list was reachable but empty;
the read-only `gcloud ai model-garden models list` fallback found 28 Gemini
publisher entries and selected a qualifying GA publisher model. That preflight
artifact records `model_invocation_performed: false`; subsequent synthetic
provider probes are recorded separately in
`evidence/adk-workflow-smoke.json`, `evidence/model-armor-measurement.json`,
and `evidence/gemma-tripwire-measurement.json`. Cloud Billing API metadata is
currently a warning because that optional API is disabled; it was not enabled
solely for this check.

No real PHI, payer credential, member ID, or service-account key was used or
added to the repository. Raw synthetic FHIR output is kept only in the ignored
`.cache/synthea/` directory.

The real-denial workstream now has three manually acquired local candidates: the
official Michigan DIFS PRIRA order `BCC_237502.pdf`, the NY DFS external appeals
export `peasadata.xlsx`, and Oregon's IRO Case Detail Report
`oregon-iro-case-detail-report.xlsx`. Their metadata, hashes, schema
inspections, privacy-scan results, and terms decisions are recorded in
`evidence/manual-review-acquisition.json`,
`evidence/ny-dfs-export-acquisition.json`, and
`evidence/oregon-iro-acquisition.json`; the Oregon local-use decision is in
`evidence/oregon-acceptance.json`. None of the raw artifacts is in the
repository. The Michigan file is a regulator order that quotes the insurer's
denial rationale, not the original denial letter. The NY workbook contains
61,606 all-years case-summary rows and outcome fields, but its privacy scan found
unreviewed identifier-shaped candidates and its reuse licence is not
established. The Oregon workbook contains 2,230 case-detail rows and an
explicit `Case Outcome` field. Under the project owner's direction, all 1,640
completed-review outcome rows are accepted for local-only external-review
evaluation; this does not label them as prior authorization or authorize
redistribution. The fail-closed adapter preflight has now exercised the case
state machine for all 1,640 rows and recorded 1,640 explicit abstentions before
denial parsing. No real regulator case has completed Appeal, and there are
still zero regulator-ground-truth comparison results.

The primary public source is now the official CMS Qualified Independent
Contractor (QIC) Decision Search API. It is a live, machine-readable source
with explicit Part C and Part D decision, appeal-type, rationale, coverage-rule,
condition, requested-item/drug, and date fields. At the 2026-08-28 inspection
it reported 901,471 Part C records and 240,958 Part D records. The
metadata-only acceptance record is `evidence/cms-qic-decision-search.json`,
and the source decision and field boundary are in
`docs/cms-qic-decision-benchmark.md`. No CMS API rows or narrative values are
committed.

CMS is accepted for regulator-summary benchmarking, not the full-case track.
The public source does not expose the original denial letter, complete
clinical evidence, internal appeal package, or original plan-policy version.
The project therefore has a real public source for the outcome/rationale lane,
while full Appeal evaluations remain zero until a complete package exists.

## Local product path — current

The data track is now frozen. The repository has started the product layer with
a local deterministic seven-role graph: Intake, Denial Parser, Policy Analyst,
Evidence Miner, Argument Builder, Deadline Sentinel, and Escalation Strategist.
The graph is wrapped by the four-veto combinator and the single-mutation
submission gate. It supports quarantine, the Evidence Floor, clinician
co-signature, a case-bound statutory clock, and hash-chained local receipts.
The local runtime also exposes reference-only event delivery, case-scoped
memory, an independent payer adjudicator, and a reversibility journal.

This is an executable local fallback, and the same deterministic HTTP facade
is now deployed as a synthetic-only Cloud Run service. It is not a deployed
ADK application, dedicated Gemma GPU endpoint, or managed Agent Runtime workflow. A
synthetic seven-agent ADK smoke run has completed and is recorded in
`evidence/adk-workflow-smoke.json`; it is not a full appeal case evaluation. A
separate managed Model Armor synthetic measurement has run and is recorded in
`evidence/model-armor-measurement.json`, and a serverless Gemma MaaS synthetic
measurement is recorded in `evidence/gemma-tripwire-measurement.json`; neither
was the default workflow boundary in the earlier deployed revision. Commit
`ac7ef24` added a managed Model Armor -> Gemma boundary to the workflow, and
revision `appeal-backend-00014-95f` has now passed a hosted synthetic clean
case through inbound, egress, and memory checks. A synthetic injection was
blocked at inbound and quarantined before denial parsing. A real synthetic ADK
case exit using an
image-only PDF is recorded in `evidence/adk-stage-b-case-exit.json`; it still
does not claim a managed Agent Runtime deployment or a full Appeal evaluation.
The current limitations are recorded in
[`docs/LIMITATIONS.md`](LIMITATIONS.md). The local synthetic smoke command is:

```text
make run-local-workflow
```

The full local runtime path, including a synthetic payer determination, is:

```text
make run-local-runtime
```

For loopback HTTP integration testing, use `make run-local-api`; it is
explicitly unauthenticated and is not a public deployment.

Use `scripts/run_local_workflow.py --approve` for the co-signed path,
`--inject` for the quarantine path, and `--missing-evidence` for the
Evidence Floor abstention path. Reports and receipts default outside the
repository. Scoring remains intentionally deferred until the agent workflow
is complete; see the local-only scoring handoff in the workspace.

The dated official Part D bulk CSV fallback was downloaded unchanged outside
the repository after confirming local disk space. Its 240,958 rows, 894,397,692
bytes, ETag, and SHA-256 are recorded in
`evidence/cms-qic-part-d-bulk-inspection.json`. The streaming inspector mapped
the title-cased bulk headers to the API schema, found no malformed rows, and
found that the bulk file omits `record_number`. Its technical privacy scan
found 453 hashed candidate locators: 14 date-of-birth labels, 13 email-shaped
values, 246 member-ID labels, two phone-shaped values, and 181 physical-
address-shaped values. Privacy, stable-identity, reuse, and acceptance gates
for the full file remain closed; no raw bulk rows were committed. Under the
explicit workspace-owner decision recorded in
`evidence/cms-qic-part-d-bulk-acceptance.json`, all 192 `f` candidate groups
were included and all 42 `b`/`l` groups were excluded, yielding 240,916 rows
accepted for local regulator-summary evaluation only. The source-native
`record_number` remains absent; the manifest documents pinned-file content
identity using file SHA-256 plus row SHA-256 and occurrence disambiguation for
duplicate content rows.
The assistant-delegated proposal at
`/Users/user/Downloads/cms-qic-partd-privacy-decisions-agent-proposed.json`
is preserved as the metadata-only decision input.

The official DMHC IMR download and API remain Cloudflare-protected. A public
Kaggle mirror was downloaded outside the repository and inspected as a blocked
fallback candidate: 19,245 rows and 11 columns, with `Reference ID`,
`Determination`, `Findings`, and treatment categories. Its technical scan found
22 physical-address-shaped values; no narrative rows are accepted. The
metadata-only acquisition record is `evidence/dmhc-kaggle-acquisition.json`.
A published third-party case example is a lead, not an official payload.
California DWC was investigated and rejected as a primary source because it is
workers' compensation and does not expose the complete denial packet needed by
this benchmark.

## Release tracks (2026-08-28)

The real-data release is intentionally split into two tracks:

- `regulator_outcome_benchmark` — real regulator determinations and summary
  findings. This can support outcome/rationale benchmarking when the selected
  source's provenance, reuse, privacy, and field semantics are accepted. It
  does not claim to contain the original denial letter, internal appeal, raw
  clinical evidence, policy version, or prior-authorization proof. Its
  current acceptance record is
  [`evidence/cms-qic-decision-search.json`](../evidence/cms-qic-decision-search.json),
  with the source implementation boundary in
  [`cms-qic-decision-benchmark.md`](cms-qic-decision-benchmark.md).
- `full_appeal_case_corpus` — complete de-identified case packages containing
  the denial, policy context, clinical evidence, internal appeal, external
  review, and final outcome. This requires an authorized data partner and a
  written reuse/privacy decision. Its acceptance record is
  [`evidence/full-appeal-case-corpus-acceptance.json`](../evidence/full-appeal-case-corpus-acceptance.json),
  and the acquisition brief is
  [`docs/full-appeal-corpus-acquisition.md`](full-appeal-corpus-acquisition.md).

### Data track closure

The source investigation is complete for this build. Do not open a new
Washington, NY DFS, Oregon, DMHC, Kaggle, or full-case acquisition
investigation. The CMS summary subset, payer-policy registry, Synthea/HAPI
fixture, and CMS-0057-F clock configuration are the frozen inputs. Unresolved
source questions remain recorded in [`docs/DATA_PROVENANCE.md`](DATA_PROVENANCE.md)
and [`docs/LIMITATIONS.md`](LIMITATIONS.md); they are no longer work items.

## Google Cloud hosting status

The deterministic Appeal HTTP backend is deployed to Cloud Run in project
`onyx-yeti-506606-i9` (display name `Appeal`), region `europe-west2`, revision
`appeal-backend-00014-95f`, with 100% traffic on that revision. The verified
service URL is
<https://appeal-backend-hhcjpefk2q-nw.a.run.app>. The `/api/healthz` endpoint
returned `status: ok` with `storage: firestore` and
`security: managed_model_armor_gemma`. A hosted synthetic case completed
creation, clinician approval, one submission mutation, and payer adjudication
to `CLOSED_WON`; a subsequent board request read persisted synthetic cases.
The aggregate-only deployment record is
`evidence/cloud-run-deployment.json`; the narrative audit is
`docs/audits/cloud-persistence.md`; the managed security audit is
`docs/audits/managed-security-cloud-run.md`.

The Cloud Run service is intentionally unauthenticated and synthetic-only. No
real case data was uploaded. Firestore persists the immutable case state, safe
references, a reference-only workflow session, and the hash-chained receipt
ledger. A synthetic case created on revision `00012-rh7` was approved after
`00013-qzz` replaced the container and adjudicated after `00014-95f` replaced
it again, ending in `CLOSED_WON` with one external mutation. This establishes
the hosted Google Cloud backend and restart-safe Firestore workflow boundary,
but it does not establish Agent Runtime, Agent Registry, Agent Identity,
Pub/Sub, Memory Bank, Gateway, Firebase Auth, or managed Observability
deployment. The hosted Model Armor/Gemma boundary is verified for synthetic
workflow inputs; it is not a full Appeal evaluation.

Cloud Scheduler job `appeal-deadline-sentinel` is enabled in `europe-west2`
with an hourly UTC cadence and an OIDC token for
`appeal-scheduler@onyx-yeti-506606-i9.iam.gserviceaccount.com`. The protected
route rejected an anonymous request with 401; a manual run of the real job
returned 200 and closed two synthetic expired cases. The audit is
`docs/audits/deadline-sentinel.md`.

Before any real-data upload or managed-service expansion, run a live inventory
against the approved project and record the results:

```text
gcloud run services list --project=onyx-yeti-506606-i9
gcloud storage buckets list --project=onyx-yeti-506606-i9
gcloud artifacts repositories list --project=onyx-yeti-506606-i9
gcloud sql instances list --project=onyx-yeti-506606-i9
```

Do not upload raw case material to Google Cloud until the full-case acceptance
manifest names the permitted storage location and records access, retention,
deletion, and audit controls.

## Done and verified

- Live discovery scaffolding and the current preflight artifact for
  `onyx-yeti-506606-i9` are in `scripts/preflight.py`, `docs/preflight.json`,
  and `docs/audits/phase-0.md`. The original `appeal-fleet-2026-0825` result
  remains in the audit as a historical snapshot only. The preflight uses the
  live Model Garden publisher catalog when the generic custom-model list is
  empty, without invoking a model.
- Official-source discovery and fail-closed retrieval scaffolding are in
  `config/real_corpus_sources.json`, `config/policy_sources.json`,
  `scripts/fetch_public_source.py`, `docs/audits/precredit-imr.md`, and
  `docs/audits/precredit-policy-source.md`.
- The explicit case state machine, idempotency rules, clinician-signature
  requirement, deadline refusal for unverified clocks, and stable fingerprint
  are in `src/appeal_core/state_machine.py`.
- The append-only, hash-chained receipt ledger and verifier are in
  `src/appeal_core/ledger.py` and `scripts/verify_ledger.py`.
- The deterministic criterion tree evaluator and Evidence Floor validation are
  in `src/appeal_core/criteria.py`. The Argument Builder cannot be represented
  as having clinical evidence unless an Evidence Miner observation supplies a
  FHIR reference.
- The local test suite has 74 passing tests, and strict mypy has passed for the
  core package. Re-run both after any changes.
- One official Michigan PRIRA order was manually downloaded and inspected. The
  result is in `evidence/manual-review-acquisition.json`; it counts as one
  local regulator-order candidate, not as an evaluation result.
- One official NY DFS all-years Excel export was manually downloaded and
  inspected with `scripts/inspect_ny_export.py`. It has 61,606 rows, 19 columns,
  `Appeal Decision` outcomes, and a `Denial Reason` field but no explicit
  `Appeal Type` column. The raw workbook remains outside the repository, and
  the metadata-only result is in `evidence/ny-dfs-export-acquisition.json`.
  Identifier candidates and reuse status keep it out of the accepted evaluation
  corpus.
- One official Oregon IRO Case Detail Report was downloaded unchanged and
  inspected with `scripts/inspect_oregon_iro.py`. It has 2,230 rows, nine
  observed fields, and an explicit `Case Outcome` field. The raw workbook
  remains outside the repository; `evidence/oregon-iro-acquisition.json` is
  metadata-only. `evidence/oregon-acceptance.json` records the project-owner
  decision to use 1,640 completed-review rows locally, while
  `docs/oregon-iro-review-request.md` remains an optional request for redacted
  synopses and written confirmation. `scripts/run_oregon_local_evaluation.py`
  has since run the adapter preflight across those rows; the aggregate report
  records 1,640 abstentions and zero full Appeal evaluations.

- Synthea v4.0.0, the JAR digest, both seeds, fixed dates, California geography,
  and a one-thread bounded invocation are now pinned. The corrected fixed-end
  invocation passed regeneration at 25, 100, and 300 requested patients. The
  full run produced 342 patient bundles and its aggregate manifest and
  byte-identical comparison are recorded in `evidence/corpus.json`.
- HAPI FHIR is pinned to `hapiproject/hapi:v8.10.0-3` by image digest in
  `config/requirements.json`. The R4 application configuration and standard
  library load/verify scripts are in `config/hapi.application.yaml`,
  `scripts/load_synthea_corpus.py`, and `scripts/verify_hapi_load.py`. A local
  HAPI R4 instance accepted all 342 manifest-tracked transaction bundles with
  HTTP 200 responses using a 5 GiB JVM heap. `evidence/hapi-load-full.json`
  records the aggregate load, and `evidence/hapi-verify.json` records an exact
  match for every expected source resource count. HAPI also reports 830
  generated `Practitioner` placeholder resources for unresolved references;
  those are explicitly unexpected server-side resources and are not part of
  the source manifest. A subsequent file-backed H2 restart test failed with
  `Chunk 15190 not found`, so durable H2 persistence is not an accepted
  configuration; recreate a fresh in-memory HAPI instance for another load.
- The aggregate-only Synthea evidence review is in
  `scripts/inspect_synthea_distribution.py` and
  `evidence/synthea-distribution.json`. It confirms 342 patient bundles and
  reports per-resource patient coverage, coded/value-bearing counts, and
  statuses without emitting identifiers or narrative text. It does not claim
  policy-criterion sufficiency or real-denial ground truth.
- The CMS summary adapter preflight is implemented in
  `scripts/run_cms_qic_summary_evaluation.py` and has processed three live Part
  D rows. Its aggregate report is `evidence/cms-qic-summary-evaluation.json`:
  three explicit regulator outcomes were observed, three rows abstained before
  full Appeal inputs, and zero Appeal evaluations or comparisons were claimed.
- The CMS full-scope privacy gate is implemented in
  `scripts/scan_cms_qic_privacy.py`. A full Part D extraction stopped on a
  privacy-shaped value before acceptance and retained no partial output. The
  scanner was then started but not completed; therefore
  `evidence/cms-qic-part-d-privacy-scan.json` does not exist yet. The API
  accepted 1,000-row pages but rejected 5,000- and 10,000-row pages with HTTP
  400. The official bulk CSV endpoint returned HTTP 200 with an ETag during a
  header check; the subsequent full bulk fallback inspection is recorded
  separately below.
- The bulk fallback is implemented in `scripts/inspect_cms_qic_bulk.py` and
  its terminal-only human review helper is
  `scripts/review_cms_qic_bulk_privacy.py`. The unchanged Part D CSV was
  scanned in full and the aggregate report is
  `evidence/cms-qic-part-d-bulk-inspection.json`; it is blocked because the
  source omits `record_number` and has 453 technical privacy candidates. The
  full artifact remains blocked as-is, while
  `evidence/cms-qic-part-d-bulk-acceptance.json` records the accepted
  240,916-row local-summary subset and its 42-row exclusion.
- `scripts/propose_cms_qic_bulk_privacy.py` provides an assistant-delegated,
  conservative technical triage of those candidates. The workspace-owner
  decision records all 192 `f` groups as included and all 42 `b`/`l` groups as
  excluded without individual review; the proposal remains outside the
  repository and contains no raw values.
- `scripts/accept_cms_qic_bulk.py` validates that decision against the pinned
  CSV and writes the metadata-only acceptance manifest. It uses file SHA-256
  plus row SHA-256 as pinned-file content identity, with occurrence order only
  to disambiguate duplicate content rows; it does not invent `record_number`.

### NY DFS schema mismatch — frozen historical record

The NY DFS website displays an `Appeal Type` filter, but the downloaded workbook
contains `Denial Reason` instead and does not contain an `Appeal Type` column.
The category counts also differ between the rendered page and the workbook, so
the two fields must not be treated as equivalent from naming alone. Do not add a
guessed column or rename `Denial Reason` to `Appeal Type`.

This section is retained as historical evidence only. It is not current work;
do not resume the NY investigation while the data-acquisition freeze is in
effect. If the owner later reopens it, use this order:

1. Keep `peasadata.xlsx` unchanged in Downloads and keep its recorded hash.
2. Obtain official confirmation or documentation explaining whether the export's
   `Denial Reason` is the source equivalent of the archive's `Appeal Type`.
   A comparison of a small set of website-filtered rows is useful evidence, but
   it is not a substitute for confirmation if the counts remain different.
3. In the application schema, keep `appeal_type` nullable and use
   `denial_reason` as the only currently verified category. Any mapping must be
   recorded as verified or unresolved; never silently coerce the names.
4. Complete the privacy review of the 140 physical-address-shaped values, 8
   date-of-birth labels, and 9 member-ID labels, and resolve the unresolved reuse
   position before accepting any rows.
5. Only after those checks, select a reviewed subset relevant to prior
   authorization and run the real-denial evaluation. The Oregon adapter
   preflight is complete, but all 1,640 rows abstained before denial parsing;
   full Appeal evaluations and regulator-ground-truth comparisons remain zero.

The repository now has a fail-closed review workflow for this gate:

- `make prepare-ny-dfs-review` verifies the unchanged workbook hash and writes
  a local-only privacy packet containing cell locators, value hashes, lengths,
  and match categories. It refuses to write inside the repository and never
  writes raw narrative values.
- `make review-ny-dfs-privacy` presents those candidates to an authorized human
  reviewer in the terminal and saves only hashed decisions outside the
  repository. A partial or unresolved review does not clear the privacy gate.
- `docs/ny-dfs-review-request.md` records the request sent to NY DFS for
  official schema and reuse confirmation. Do not attach the workbook or case
  narratives; record any reply when it arrives.
- `evidence/ny-dfs-acceptance.json` is the metadata-only decision manifest.
  `make validate-ny-dfs` checks its shape; `make require-ny-dfs-ready` must fail
  until mapping, privacy, reuse, and prior-authorization review are explicitly
  recorded.

### CMS QIC decision-summary benchmark — current primary

The official CMS QIC Decision Search API is the selected public source for
real regulator-summary benchmarking. The catalog and datastore API expose the
Part C and Part D datasets without requiring a bulk CSV download. The live
inspection recorded 901,471 Part C records and 240,958 Part D records, and
confirmed the expected schemas in both datasets.

The source record and field-level boundary are:

- `evidence/cms-qic-decision-search.json` — live counts, dataset identifiers,
  schema checks, bounded privacy scan, and acceptance decision;
- `docs/cms-qic-decision-benchmark.md` — mappings, query template, storage
  rules, and the full-case limitation;
- `scripts/inspect_cms_qic.py` — metadata-only catalog/API inspector;
- `scripts/fetch_cms_qic_summary.py` — atomic, paginated, local-only
  normalized extractor;
- `scripts/scan_cms_qic_privacy.py` — full-scope, row-free privacy scanner;
- `config/real_corpus_sources.json` — allow-listed source metadata.

To refresh the aggregate evidence, supply the public ACA value shown by the CMS
QIC page. The value is used only for the request and is not written to disk:

```text
APPEAL_CMS_QIC_ACA='<public ACA value>' make inspect-cms-qic
```

The inspector reads three rows from each dataset, records only field names,
counts, and pattern totals, and writes no case text. The API's reported counts
cover the complete current API scope; the bounded read is only the schema and
privacy check. A future local extraction must page rows into an outside-
repository file and hash that file without emitting its values.

The CMS fields map as follows: `decision` is the explicit regulator outcome;
`appeal_type` is used directly; `decision_rationale` is a regulator-authored
summary and is not `denial_reason`; `coverage_rules` is summarized policy
context and not the original plan policy version; and clinical evidence and
prior-authorization status remain nullable. No CMS summary row may be joined
to a Synthea patient.

This source is ready for the summary adapter. The adapter preflight has now
processed three real Part D rows from an outside-repository extraction; all
three had explicit source outcomes and all three abstained before full Appeal
inputs. The aggregate report is
`evidence/cms-qic-summary-evaluation.json`. No summary-level comparison or
full Appeal evaluation has run. Current counts are therefore 1,142,429
available summary records, three preflight rows processed, zero summary cases
evaluated, zero full Appeal cases, and zero regulator-ground-truth comparisons.

The first full Part D extraction attempt stopped on a privacy-shaped value and
left no partial output. Run `make scan-cms-qic-privacy` before retrying the
full extraction. Its report contains only hashed locators and aggregate
categories; any candidate still requires human review. The API rejected
10,000- and 5,000-row requests with HTTP 400; use the validated 1,000-row
page size unless a future source check confirms a different limit.

### Washington OIC public IRO search — frozen historical record

The official Washington OIC currently advertises a public independent-review
decision search by company, diagnosis, treatment, decision, and reason for
appeal. The official entry points and the stale-link observation are recorded
in [`evidence/wa-oic-iro-search.json`](../evidence/wa-oic-iro-search.json).
The current search endpoint or export has not been resolved from this
workspace, so no Washington rows, schema, privacy result, or reuse permission
is claimed. Resolve the current link first, then capture one bounded result or
export outside the repository and run a source-specific inspection before
acceptance.

This was a parallel public-summary check, but it is frozen for this build and
does not delay the product work. It also cannot satisfy the full-case track
without the original denial, clinical evidence, policy version, and appeal
package.

### DMHC secondary real-source path — frozen historical record

DMHC remains a secondary retrieval path because it is directly about health-plan
denials and its official description says the IMR database contains decisions
since January 1, 2001. The source is not yet a complete accepted corpus: the
case-level file has not been downloaded, its schema has not been inspected, and
prior-authorization scope, privacy, and reuse still require explicit review.
Do not treat the CC BY metadata or the third-party `MN22-37709` write-up as a
substitute for inspecting the official file.

Use the current official catalog record:

```text
https://lab.data.ca.gov/dataset/independent-medical-review-imr-determinations-trend
```

If an authorized browser or network can download the CSV, save it unchanged
outside the repository, then run:

```text
make inspect-dmhc-imr \
  DMHC_IMR_INPUT=../Downloads/independent-medical-review-determinations-trends.csv \
  DMHC_IMR_REPORT=evidence/dmhc-imr-acquisition.json
```

The inspector does not print case numbers, treatment text, findings, or other
cell values. Review its aggregate report before creating a DMHC acceptance
manifest. Acceptance requires, at minimum, an observed regulator outcome,
denial basis, requested service, clinical/findings field, a defensible
prior-authorization scope decision, a technical privacy review, and a
source-specific reuse decision. Until those checks pass, keep the CSV local,
keep `appeal_type` nullable unless officially established, and keep Appeal
evaluation and regulator comparisons at zero.

The official portal/API was not usable from either the workspace or the user's
browser, so the fallback copy is currently at:

```text
/Users/user/Downloads/dmhc-imr-kaggle-ca-independent-medical-review-2023-11-20.zip
/Users/user/Downloads/dmhc-imr-kaggle-ca-independent-medical-review-2023-11-20.csv
```

The Kaggle copy is not the current official DMHC export. Its card declares a
CC0 licence and claims DMHC as the original source, but that declaration is
third-party provenance, not official permission. Reconcile it against the
official data dictionary or a future official payload before treating it as
regulator ground truth.

### Oregon IRO case-detail fallback

Oregon is an outcome-only fallback while the CMS summary path is pending. Its official
report already exposes a case-level `Case Outcome` and
does not require guessing whether `Denial Reason` means `Appeal Type`. The
project owner has accepted the 1,640 completed-review outcome rows for local
only evaluation. This does not claim prior-authorization eligibility, written
regulator permission, or redistribution rights.

The local candidate is represented by:

- `/Users/user/Downloads/oregon-iro-case-detail-report.xlsx` — unchanged raw
  workbook, local-only, SHA-256 recorded in `evidence/oregon-iro-acquisition.json`;
- `scripts/inspect_oregon_iro.py` — aggregate-only inspection; it does not emit
  case numbers, treatment values, or narrative text;
- `evidence/oregon-iro-acquisition.json` — schema, hash, and aggregate counts;
- `evidence/oregon-acceptance.json` — operator decision, scope, field mapping,
  and local-only gates;
- `/Users/user/Downloads/oregon-iro-local-evaluation.json` — generated local
  input with 1,640 selected records; contains free text and stays outside Git;
- `docs/oregon-iro-review-request.md` — optional follow-up to
  `Exreview.Ins@dcbs.oregon.gov`.

When the Oregon office responds, record the response hash and any additional
conditions. The current run uses only the public workbook under the project
owner's local-only decision; raw workbook, case numbers, and free-text rows stay
outside Git. If the office denies reuse, stop local narrative processing and
retain only the aggregate evidence already committed.

To reproduce the metadata inspection:

```text
make inspect-oregon-iro \
  OREGON_IRO_INPUT=../Downloads/oregon-iro-case-detail-report.xlsx
```

To prepare the accepted local-only input for the Appeal adapter:

```text
make prepare-oregon-local-evaluation \
  OREGON_IRO_INPUT=../Downloads/oregon-iro-case-detail-report.xlsx \
  OREGON_IRO_LOCAL_OUTPUT=../Downloads/oregon-iro-local-evaluation.json
```

The command verifies the workbook hash, selects all 1,640 completed-review
outcomes, and writes treatment text only to the outside-repository output path.
It does not run the full Appeal workflow or produce an evaluation score.

To run the fail-closed adapter preflight against that local input:

```text
make run-oregon-local-evaluation \
  OREGON_IRO_LOCAL_OUTPUT=../Downloads/oregon-iro-local-evaluation.json
```

The preflight exercises the actual case state machine and records every row as
`PARSE_FAILED_HUMAN_REVIEW`: the Oregon report has no denial narrative, policy
reference, or clinical evidence. Its aggregate-only result is in
`evidence/oregon-evaluation.json`; it deliberately leaves full Appeal
evaluation and outcome comparison at zero. The next implementation step is a
real Appeal adapter only after those required inputs are available.

### Reproducibility investigation

The first failed comparison was diagnostic, not random. Synthea's official CLI
source shows that `-r` sets the simulation reference time while `-e` separately
sets the simulation end time. Omitting `-e` left the end time at the process
wall clock, which changed active encounter, Claim, and ExplanationOfBenefit
timestamps between runs. Synthea also emits hospital/practitioner metadata
filenames containing a runtime timestamp. See the
[official Synthea CLI source](https://raw.githubusercontent.com/synthetichealth/synthea/master/src/main/java/App.java),
especially the `-cs`, `-r`, and `-e` option handling.

The correction is to pin both seeds, `-r`, and `-e`, pass the positional
`California` geography, use one generator thread under the bounded container
limit, and fingerprint only patient FHIR bundles. The corrected invocation
passed twice at 25, 100, and 300 requested patients. A prior full-scale attempt
was stopped because it was consuming too much Mac memory; it reached module
startup and emitted only a few small files, not a partial patient corpus.

Smoke settings and result:

```text
Docker limit: 2 GiB memory, 1 CPU
JVM heap: -Xmx1400m
Synthea: v4.0.0, -s 24082501, -cs 24082502, -p 5,
         -r 20260826, -e 20260826, thread pool 1, California
Measured fixed-end runs:
25 requested: 28 bundles, about 94 MiB per output; identical=true
100 requested: 113 bundles, about 418 MiB per output; identical=true
300 requested: 342 bundles, about 1.1 GiB per output; identical=true
Full fingerprint: c5c6b666f0cb8840a47934fdc0dbfbb4bf8b09dc60c2fe100fadc053e7548649
```

The raw export directories can contain Synthea hospital/practitioner metadata
whose filenames include runtime timestamps. The recorder deliberately excludes
those metadata files and compares the patient FHIR bundle set, which is the
corpus consumed by Appeal. The full-scale run must use this same documented
scope. The resulting full manifest records 342 patient bundles, aggregate FHIR
resource counts, condition distribution, tracked hashes, and an identical
regeneration comparison in `evidence/corpus.json`.

The local synthetic data-plane milestone is complete for the verified session:
the exact bundle set was loaded into the pinned HAPI instance, aggregate counts
matched, and the aggregate evidence distribution was reviewed without copying
raw FHIR data into the repository. HAPI's default database is in-memory; the
successful load reports are the durable evidence, not a claim that the live
server survives restart.

## Still outstanding

The source-acquisition track is closed. The managed Model Armor -> Gemma
boundary is now deployed and verified on synthetic inputs. The remaining work
is product construction and verification, in this order:

1. Replace the in-process event reference with the Pub/Sub event spine. Keep
   the Deadline Sentinel on its real hourly Cloud Scheduler cadence and extend
   the receipt trail across transitions.
2. Deploy the seven-role workflow through the managed Google agent platform:
   ADK execution, Agent Registry, Agent Identity, Gateway, Policies, Memory
   Bank, and Observability. Probe each approved service once; if a component
   is unavailable, record the limitation and continue with the smallest
   truthful implementation.
3. Separate the payer adjudicator into its own Cloud Run service and service
   account, validate the PAS behavior at the level actually implemented, and
   retain the deterministic Veto Combinator and single-mutation gate.
4. Build the hosted console: Firebase Auth, live statutory clock, contradiction
   view, clinician co-signature, case timeline, reasoning chain, quarantine
   display, and the asynchronous escalation path.
5. Create traceable criterion trees from the already-selected permitted payer
   policy corpus, hand-validate a sample, and record the agreement rate. This
   does not authorize a new policy-source investigation.
6. Only after the workflow is complete, resume the uncommitted local scoring
   handoff in `docs/SCORING_HANDOFF_LOCAL.md`: deterministic tree grading,
   random-criterion and generic-template controls, policy/evidence ablations,
   model-versus-tree adjudication, failure reporting, and the named-catch
   human stop. Until then, full Appeal evaluations remain zero and no scoring
   artifact should be committed.
7. Finish the demo tenant, architecture/judging documentation, video, and
   submission checks from the continuation specification. Every claimed
   number must point to committed evidence, and every missing capability must
   remain in `docs/LIMITATIONS.md`.

## Data-acquisition record — completed decision (not current work)

The bulk choice from the previous checkpoint has been completed. The official
Part D CSV is preserved unchanged at
`/Users/user/Downloads/cms-qic-partd-2026-08-25.csv`, with 894,397,692 bytes and
SHA-256
`e32b4f10eb51df1882fc3b9084807e448d4924c0605518afd71a7e85ebb9759f`.
`scripts/inspect_cms_qic_bulk.py` scanned all 240,958 rows and wrote the
aggregate-only report `evidence/cms-qic-part-d-bulk-inspection.json`. It found
453 hashed privacy candidates and a missing `record_number`. The explicit
owner policy is recorded in
`evidence/cms-qic-part-d-bulk-acceptance.json`: 240,916 rows retained, 42
rows excluded, and the source-native identifier intentionally unresolved.

The assistant-delegated technical triage is in
`/Users/user/Downloads/cms-qic-partd-privacy-decisions-agent-proposed.json`.
It records the 234 metadata-only proposals that supplied the explicit policy
decision (7 block, 192 false positive, 35 legal review). Its SHA-256 is
`ce964941ff7a32d19dfe4564b34b6937a55a284601c14f81fa7b71d018a4d497`.

The bulk acceptance step is complete. The terminal-only reviewer remains
available only if the exclusion policy is later changed:

```text
make review-cms-qic-bulk \
  CMS_QIC_BULK_INPUT=../Downloads/cms-qic-partd-2026-08-25.csv \
  CMS_QIC_BULK_REPORT=evidence/cms-qic-part-d-bulk-inspection.json \
  CMS_QIC_BULK_PRIVACY_DECISIONS=../Downloads/cms-qic-partd-privacy-decisions.json
```

The reviewer shows candidate values only in the terminal and writes hashed
decisions outside the repository. The accepted scope is local regulator-summary
evaluation only; it is not a full Appeal case corpus. Do not upload the raw CSV
or normalized narrative rows to Google Cloud or GitHub.

## Resume checkpoint — next continuation

Last verified: 2026-08-29. Resume from `/Users/user/appeal` with the active
Google Cloud project `onyx-yeti-506606-i9` (`835653516606`) and region
`europe-west2`. Do not switch back to `appeal-fleet-2026-0825`. ADC is already
working; do not run `gcloud auth application-default login` again.

The managed Model Armor -> Gemma boundary and reference-only durable workflow
session/receipt boundary are deployed and verified on Cloud Run revision
`appeal-backend-00014-95f`. The next continuation is the Pub/Sub event spine.
Start with:

```text
cd /Users/user/appeal
git pull --ff-only origin main
make test
make typecheck
```

If you need to confirm the hosted checkpoint:

```text
curl -sS https://appeal-backend-hhcjpefk2q-nw.a.run.app/api/healthz
gcloud run revisions list \
  --service=appeal-backend \
  --region=europe-west2 \
  --project=onyx-yeti-506606-i9 \
  --limit=3
```

Expected hosted health includes `status: ok`, `storage: firestore`, and
`security: managed_model_armor_gemma`. The clean and injection smoke results
are recorded in `docs/audits/managed-security-cloud-run.md` and
`evidence/cloud-run-deployment.json`.

Continue with Pub/Sub transitions, managed agent-platform components, the
separate payer service, and the hosted console. The ordered backlog is in
`## Still outstanding` above. Keep all inputs synthetic and aggregate-only.

Do not resume the CMS, NY, Washington, DMHC, Oregon, or full-case acquisition
work. Do not run the scoring handoff yet. `docs/SCORING_HANDOFF_LOCAL.md` is a
future, uncommitted work plan; full Appeal evaluations remain zero until the
workflow and required inputs genuinely exist.

## Push status

The public repository remote is already configured. Commits through
`0cf91c4` are on `origin/main`; the receipt persistence commit `e34d1f4` is
present locally but has not pushed because this environment cannot resolve
`github.com` from either network path:

```text
git remote -v
git push origin main
```

Do not put credentials, tokens, or key files in the repository or command
history. A GitHub CLI or browser-authenticated remote is preferred.

## Safe continuation order

The authoritative continuation commands are in the checkpoint above. For a
local verification-only check, use:

```text
cd /Users/user/appeal
make test
make typecheck
git status --short
```

Do not regenerate the HAPI corpus or refresh source preflight merely to resume
the product build. Preserve aggregate-only evidence and keep the deployment
synthetic-only until the required controls and permissions are verified.
