# APPEAL build handoff

Updated: 2026-08-27

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

The real-denial workstream now has two manually acquired local candidates: the
official Michigan DIFS PRIRA order `BCC_237502.pdf` and the NY DFS external
appeals export `peasadata.xlsx`. Their metadata, hashes, schema inspections,
privacy reviews, and terms decisions are recorded in
`evidence/manual-review-acquisition.json` and
`evidence/ny-dfs-export-acquisition.json`. Neither raw artifact is in the
repository. The Michigan file is a regulator order that quotes the insurer's
denial rationale, not the original denial letter. The NY workbook contains
61,606 all-years case-summary rows and outcome fields, but its privacy scan found
unreviewed identifier-shaped candidates and its reuse licence is not
established. Both remain local-only pending review. No real regulator case has
been run through Appeal, and there are still zero regulator-ground-truth
comparison results.

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
- The local test suite has 16 passing tests, and strict mypy has passed for the
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
   authorization and run the real-denial evaluation. Until then the counts stay
   at zero Appeal evaluations and zero regulator-ground-truth comparisons.

The repository now has a fail-closed review workflow for this gate:

- `make prepare-ny-dfs-review` verifies the unchanged workbook hash and writes
  a local-only privacy packet containing cell locators, value hashes, lengths,
  and match categories. It refuses to write inside the repository and never
  writes raw narrative values.
- `make review-ny-dfs-privacy` presents those candidates to an authorized human
  reviewer in the terminal and saves only hashed decisions outside the
  repository. A partial or unresolved review does not clear the privacy gate.
- `docs/ny-dfs-review-request.md` is the draft request for official schema and
  reuse confirmation. Do not attach the workbook or case narratives.
- `evidence/ny-dfs-acceptance.json` is the metadata-only decision manifest.
  `make validate-ny-dfs` checks its shape; `make require-ny-dfs-ready` must fail
  until mapping, privacy, reuse, and prior-authorization review are explicitly
  recorded.

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

1. Resolve the real-denial source. The Michigan PRIRA order is a manually
   acquired, local-only candidate with its bytes, schema, omission review,
   terms, and hash recorded; it has not been evaluated. The NY DFS export is a
   larger local candidate, but its 140 physical-address-shaped summary values,
   date-of-birth/member-ID labels, and unresolved reuse position must be
   reviewed before any row is accepted. Its `Denial Reason` field must not be
   called `Appeal Type` until the source mapping is verified; see the resume
   instructions above. Continue with privacy/reuse review, the separate
   California Department of Insurance IMR database, and another reusable
   case-level source if needed. The tested DMHC and NY DFS routes return access
   errors, and the CDI link redirects into an unavailable/legacy application;
   all findings and URLs are documented in `docs/audits/precredit-imr.md`. Do
   not claim real regulator evaluation until Appeal has run against an accepted
   case set and the comparison is recorded. Pennsylvania, CMS, Oregon, and
   similar aggregate reports are calibration inputs only.
2. Complete policy terms review and ingest only permitted, ETag-backed policy
   documents. Extract traceable criterion trees and perform human validation.
3. Complete quota and residency probes and authenticated managed-component
   checks. The model metadata gate now passes, but the selected region and
   managed Agent Platform components are not yet fully verified.
4. Only after preflight exit: build the independent PAS payer, then the agent
   identities/tools, event spine, Memory Bank, governance boundary, Gemma,
   observability, console, evaluation, and seeded demo.
5. The Phase 9 real-denial run and mandatory human-choice stop have not happened.
   The stop cannot begin until an accepted regulator case corpus exists.

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
   current result is a passing Gemini metadata check, with four remaining
   policy/corpus blockers.
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
5. Keep Phase 1 and any Gemini generation stopped until the four blockers and
   the component, quota, and residency checks are resolved. If the Prepay
   transaction is still absent after 24 hours, capture the AI Studio Billing
   status for review instead of paying again.

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
cloud-dependent build remains gated by the four policy/corpus blockers and the
unresolved component/quota/residency checks; do not generate content or enable
additional services just to advance the preflight.
