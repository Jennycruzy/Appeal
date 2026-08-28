# APPEAL build handoff

Updated: 2026-08-28

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

The live preflight now confirms `aiplatform.googleapis.com` is enabled for
`onyx-yeti-506606-i9`. Its regional custom-model list is reachable but empty;
the read-only `gcloud ai model-garden models list` fallback found 28 Gemini
publisher entries and selected a qualifying GA publisher model. The artifact
records `model_invocation_performed: false`; no prompt, deployment, or paid
model call has been made. Cloud Billing API metadata is currently a warning
because that optional API is disabled; it was not enabled solely for this
check.

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

The CMS summary API, DMHC mirror, NY DFS export, Oregon report, and Michigan
order are not silently promoted into the full-case track. Synthea remains an
integration fixture only. Until a full-case package is accepted, full Appeal
evaluations and end-to-end regulator comparisons remain zero.

## Google Cloud hosting status

No application workload has been hosted as of the latest workspace evidence.
The project registration and API setup are real, but no Cloud Run service,
Cloud Storage bucket, database, Artifact Registry image, or real-case upload is
recorded. The historical preflight explicitly records that no application
data, database, Cloud Run service, or service-account key was created. The
current local `gcloud` profile has no active account or project, so it should be
treated as unconfigured until a fresh authenticated inventory is run.

Before any deployment or real-data upload, run a live inventory against the
approved project and record the results:

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
- The local test suite has 19 passing tests, and strict mypy has passed for the
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

### NY DFS schema mismatch — resume here

The NY DFS website displays an `Appeal Type` filter, but the downloaded workbook
contains `Denial Reason` instead and does not contain an `Appeal Type` column.
The category counts also differ between the rendered page and the workbook, so
the two fields must not be treated as equivalent from naming alone. Do not add a
guessed column or rename `Denial Reason` to `Appeal Type`.

When resuming, use this order:

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

This source is ready for the summary adapter, but no summary adapter or Appeal
comparison has run yet. Current counts are therefore 1,142,429 available
summary records, zero summary cases evaluated, zero full Appeal cases, and zero
regulator-ground-truth comparisons.

### DMHC secondary real-source path

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

1. Build and run the CMS QIC summary adapter against an explicitly selected,
   outside-repository page range. Preserve `appeal_type` and `decision` from
   the source, keep `denial_reason` and `prior_authorization` nullable unless
   row-level evidence exists, and record summary-level comparisons separately.
   The source reports 1,142,429 available records, but no summary case has yet
   been evaluated. The state machine must abstain when the Evidence Floor needs
   clinical or original-denial inputs that the summary does not contain.
2. Keep the official DMHC path, the 140 NY address-shaped values, the eight DOB
   labels, the nine member-ID labels, and NY's unresolved reuse/mapping decision
   as secondary candidates. The NY export's `Denial Reason` must not be called
   `Appeal Type` until its source mapping is verified. Oregon remains accepted
   only for local-only external-review outcomes; its 1,640-row adapter
   preflight abstained before denial parsing. Michigan remains local-only and
   unevaluated. These candidates must not be mixed with the CMS source.
3. The CMS source does not satisfy the full-case package. Obtain that package
   only through an authorized source with the requirements in
   `docs/full-appeal-corpus-acquisition.md`; do not block summary benchmarking
   on a reply-dependent request.
4. Complete policy terms review and ingest only permitted, ETag-backed policy
   documents. Extract traceable criterion trees and perform human validation.
5. Complete quota and residency probes and authenticated managed-component
   checks. The model metadata gate now passes, but the selected region and
   managed Agent Platform components are not yet fully verified.
6. Only after preflight exit: build the independent PAS payer, then the agent
   identities/tools, event spine, Memory Bank, governance boundary, Gemma,
   observability, console, evaluation, and seeded demo.
7. The Phase 9 real-denial run and mandatory human-choice stop have not
   happened. A summary adapter may produce a documented abstention, but it
   cannot claim a full Appeal evaluation without the original denial, policy,
   and clinical inputs.

## Resume checkpoint — after the PC is charged

Last verified: 2026-08-27. Resume from `/Users/user/appeal` with the active
Google Cloud project `onyx-yeti-506606-i9` (`835653516606`) and region
`europe-west2`. Do not switch back to `appeal-fleet-2026-0825`.

1. In AI Studio, open Billing for the active project and check the existing
   Cloud Prepay transaction/balance. The console already reported the $10
   payment successful and said the transaction may take up to 24 hours. Do not
   make a second payment. The separate $300 Cloud trial balance is not to be
   counted as Gemini API credit.
2. Refresh the safe cloud metadata artifact:

   ```text
   cd /Users/user/appeal
   APPEAL_GCP_REGION=europe-west2 python3.12 scripts/preflight.py
   ```

   This performs discovery/list checks only. It must not call `generateContent`,
   deploy anything, create a resource, or enable another API. The expected
   current result is a passing Gemini metadata check, with the four blockers
   recorded in that point-in-time artifact. The later Oregon local-only
   acceptance is separate and does not alter `docs/preflight.json`.
3. Run the local verification before continuing data-plane work:

   ```text
   make test
   make typecheck
   python3.12 -m py_compile scripts/preflight.py scripts/record_synthea_corpus.py
   ```

4. The synthetic HAPI milestone is complete for the verified session. The authoritative reports are
   `evidence/hapi-load-full.json`, `evidence/hapi-verify.json`, and
   `evidence/synthea-distribution.json`. If recreating the load, use an empty
   fresh in-memory HAPI database and `HAPI_TIMEOUT=1800`; use
   `HAPI_START_INDEX=N` only while that same server process retains a
   reconciled partial load, because the source transaction entries use POST and
   are not safe to replay against a populated database or after a restart.
5. Keep cloud-dependent Phase 1 work and any Gemini generation stopped until
   the remaining policy, component, quota, and residency checks are resolved.
   The Oregon local-only outcome preparation may continue without Gemini. If
   the Prepay transaction is still absent after 24 hours, capture the AI Studio
   Billing status for review instead of paying again.

## Push status

The public repository remote is already configured and the current commits are
on `origin/main`:

```text
git remote -v
git push origin main
```

Do not put credentials, tokens, or key files in the repository or command
history. A GitHub CLI or browser-authenticated remote is preferred.

## Safe continuation order

```text
cd /Users/user/appeal
make test
make typecheck
python3.12 -m py_compile scripts/preflight.py scripts/record_synthea_corpus.py
git status --short
```

Then check the running HAPI container and preserve only aggregate reports. The
cloud-dependent build remains gated by the blockers recorded in the current
preflight snapshot and the unresolved component/quota/residency checks; do not
generate content or enable additional services just to advance the preflight.
