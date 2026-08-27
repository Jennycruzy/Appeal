# Phase 0 self-audit — discovery baseline

Status: historical snapshot; superseded by the 2026-08-27 registration
addendum below. Phase 1 must not start.

Audit date: 2026-08-25

> This document preserves the original `appeal-fleet-2026-0825` discovery
> evidence. The current Appeal project is `onyx-yeti-506606-i9`; see the
> addendum below and the current `docs/preflight.json` artifact.

The live command used for this audit was:

```text
GOOGLE_CLOUD_PROJECT=appeal-fleet-2026-0825 APPEAL_GCP_REGION=europe-west2 python3.12 scripts/preflight.py
```

The command completed with exit code `2`, which is the script's explicit
fail-closed result when blockers remain. It wrote
[`docs/preflight.json`](../preflight.json), generated at
`2026-08-25T22:09:56.317666Z` in the final live run. The artifact SHA-256 for
this run is
`c09d662843ca811a40ec049c128aa1cd3725be3ea1278d76fd19f8e4c1827d9b`.

The final live run reported:

```text
Blockers: 4
BLOCKER: Gemini model discovery
BLOCKER: Policy source: aetna_cpb
BLOCKER: Policy source: cigna_policy
BLOCKER: Real corpus source: california_dmhc_imr_determinations
Preflight did not pass. Stop before Phase 1 and resolve the blockers.
```

## Checklist

- [x] `docs/preflight.json` exists and contains a UTC timestamp. Evidence: the
  file itself; `python3.12 scripts/preflight.py` prints its output path and
  writes `generated_at`.
- [ ] Every model ID in `config/` traces to a live model listing. Evidence:
  there is intentionally no `config/models.json` and no selected model ID.
  `aiplatform.googleapis.com` is enabled, and the live catalog resolved the
  current Agent Platform discovery document at
  `https://aiplatform.googleapis.com/$discovery/rest?version=v1`. The
  `projects.locations.models.list` probe at `europe-west2` returned
  `PERMISSION_DENIED: BILLING_DISABLED`. No model string was selected or
  guessed.
- [ ] Every managed Agent Platform component has an authenticated probe result.
  Evidence: the component records in `docs/preflight.json` contain public
  catalog matches and explicit fallbacks, but are `not_checked` because no
  authenticated component binding was discovered. This is an exit-criteria
  failure, not a pass by assertion.
- [x] Every component that could not be probed has a named fallback. Evidence:
  `config/platform_components.json` defines a fallback for Agent Runtime,
  Sessions, Memory Bank, Agent Registry, Agent Identity, Agent Gateway, Agent
  Policies, Model Armor, Code Execution, Agent Evaluation, and Agent
  Simulation; the values are copied into the preflight evidence.
- [x] Policy-source access was checked before document fetching. Evidence:
  `docs/preflight.json` records robots and terms HTTP results for all four
  configured sources and `policy_fetch_performed: false` for each. Aetna and
  Cigna returned robots/terms responses that do not permit automated fetching;
  UHC robots permits the index path but still requires human terms review.
  No policy document was fetched.
- [ ] The real IMR determination source is retrievable and its case-level
  schema is verified. Evidence: `config/real_corpus_sources.json` records the
  official catalogue, DMHC, CSV, dictionary, archive, and datastore URLs;
  `docs/preflight.json` records HTTP 403 for the official data endpoints. No
  IMR data was fetched or committed.
- [x] The CMS-0057-F benchmark definition is recorded from official sources.
  Evidence: `docs/preflight.json` records successful live retrieval of the CMS
  FAQ, reporting template, and final-rule fact sheet. The source is explicitly
  treated as a metric definition, not as a case-level dataset.
- [ ] An external corpus payload has been accepted into an ETag-backed cache.
  Evidence: `scripts/fetch_public_source.py` correctly rejected the DMHC CSV
  with HTTP 403 and rejected the CMS template because the successful response
  did not provide an ETag. No payload was accepted.
- [ ] Quota ceilings and demo arithmetic are both verified. Evidence: the
  preflight records the configured six-case load arithmetic, but quota ceilings
  remain `not_checked` until the regional model and managed service bindings
  are discovered.
- [x] PAS publication discovery is recorded. Evidence: the HL7 package list
  returned published Da Vinci PAS `2.2.1`, FHIR `4.0.1`, status `trial-use`,
  dated 2026-03-27. The selection reason is recorded in
  `docs/preflight.json`.
- [x] Synthea availability, licence, version candidate, and seed are recorded.
  Evidence: the live GitHub release list selected `v4.0.0`, the live licence
  endpoint reported Apache-2.0, and `config/requirements.json` records seed
  `24082501`.
- [x] The local runtime requirement is verified. Evidence:
  `python3.12 --version` reported Python `3.12.13`; `python3.12 -m py_compile
  scripts/preflight.py` passed.

## Live project evidence

The authenticated Devpost-linked Google account created a clean project:

```text
Project ID:     appeal-fleet-2026-0825
Project number: 509610029798
Name:           APPEAL Fleet 2026
State:          ACTIVE
```

The project was created through the Cloud Resource Manager API after the
account accepted the Google Cloud Terms of Service. Service Usage was enabled
through the Cloud Console, and the Agent Platform API was then enabled through
the Service Usage API. The completed enablement result is recorded in the
terminal evidence and in `docs/preflight.json`. No application data, database,
Cloud Run service, or service-account key was created.

`europe-west2` was used as a probe location because the current official Gemini
3.5 Flash model page lists it as a supported Europe location. It is not yet a
final residency selection: the live project model probe cannot complete until
billing is enabled. The source page is:
`https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-flash`.

The model probe's final live evidence is in `docs/preflight.json`:

```text
list_url: https://europe-west2-aiplatform.googleapis.com/v1/projects/appeal-fleet-2026-0825/locations/europe-west2/models
http_status: 403
error: PERMISSION_DENIED: BILLING_DISABLED
```

The real-corpus discovery evidence is also in `docs/preflight.json`. The
official DMHC catalogue was reachable, but the direct CSV, dictionary, archive,
datastore, and searchable-decision endpoints returned HTTP 403 to the live
preflight client. The CMS metric-definition endpoints returned HTTP 200. The
full source notes and manual-retrieval fallback are in
[`docs/audits/precredit-imr.md`](precredit-imr.md).
The CMS MCD policy candidate is recorded in
[`docs/audits/precredit-policy-source.md`](precredit-policy-source.md); it was
not fetched because its page presents additional licence terms.

The Mac has Google Cloud CLI `581.0.0` and a user ADC credential for the
Devpost-linked Google account. The ADC quota project was set locally to
`appeal-fleet-2026-0825`; this changed only the local ADC configuration. No
service-account key was created or stored.

## Gaps

- Billing is disabled on `appeal-fleet-2026-0825`; Agent Platform model discovery
  cannot be verified until a billing account is attached.
- `europe-west2` is only a documented probe location, not an accepted final
  residency decision. The final region must be recorded after the live model
  and agent-location probes succeed.
- Managed Agent Platform component endpoints and residency metadata are not
  yet available through an authenticated probe in this project.
- The current Agent Platform discovery documents expose publisher-model
  invocation/get operations but no publisher-model list operation in the
  discovery schema. The model-list route used by the official Gen AI SDK must
  be verified against the live project after billing is enabled; until then no
  model ID may enter `config/`.
- Quota-metric probing needs the current live service bindings and must be
  completed before deployment arithmetic is accepted.
- Aetna and Cigna policy sources are not ingestion candidates under the
  observed robots/terms responses. UHC remains pending human terms review. CMS
  MCD is a reachable candidate, but its terms review is not complete.
- The official DMHC catalogue is discovered and licensed as a public source,
  but its case-level file is currently blocked to the preflight client. A
  manual, provenance-preserving retrieval is required before Phase 1D can
  claim real regulator-determined ground truth.
- The CMS definition endpoints are reachable, but the template response did
  not include an ETag. The cache policy therefore rejects it until a
  validator-backed retrieval path is available.
- The public Synthea release endpoint initially exposed a moving
  `master-branch-latest` tag. The preflight was corrected to select a dated,
  non-prerelease release; the final evidence records `v4.0.0`.

## Blockers

1. Attach billing to `appeal-fleet-2026-0825`. The API returned the Google
   billing URL in the live error; the agent cannot choose a billing account or
   incur financial commitments on the user's behalf.
2. After billing propagates, complete the live Agent Platform model-list and
   publisher-model probes using the current discovery/SDK interface. Do not
   hardcode a model ID.
3. Select and record a region only after the live model listing proves the
   required Gemini version is available there.
4. Complete quota and residency probes, then rerun this audit artifact.
5. Obtain explicit terms permission or replace Aetna/Cigna with permitted
   policy sources before Phase 1 ingestion.
6. Retrieve and inspect the official DMHC IMR data or its official searchable
   records without modifying the source; verify the case-level rationale and
   determination fields before accepting it as the Phase 1D corpus.

## Exit criteria

Phase 0 is not complete. The model ID, component availability, region,
quotas, policy-source permissions, and DMHC case-level data access are not all
verified. The build is therefore stopped before Phase 1, as required by the
specification.

## 2026-08-27 registration addendum

The workspace has been re-registered against the project shown in the current
Cloud Console and AI Studio evidence:

```text
Project ID:     onyx-yeti-506606-i9
Project number: 835653516606
Former target:  appeal-fleet-2026-0825
Region probe:   europe-west2
```

The command used for the current live preflight was:

```text
GOOGLE_CLOUD_PROJECT=onyx-yeti-506606-i9 APPEAL_GCP_REGION=europe-west2 python3.12 scripts/preflight.py
```

The current `docs/preflight.json` records the new project, 10 passes, 16
warnings, and 4 blockers. Application Default Credentials and Service Usage
are available for project `onyx-yeti-506606-i9`, and
`aiplatform.googleapis.com` is enabled. The regional custom-model list is
reachable but empty; the preflight therefore uses the read-only Model Garden
publisher catalog and records a qualifying GA publisher model without
invoking it. The current selected metadata is
`gemini-3.7-flash@default` in the `europe-west2` resource path; this is a live
catalog result, not a generation test or a claim that residency is finalized.

The supplied AI Studio evidence shows setup complete, Gemini API Paid Tier
activated, and a successful $10 Cloud Prepay payment. The Cloud Console
evidence shows the same active project with a $300 free trial and $0 used; that
is a separate Cloud trial balance and is not treated as Gemini API credit.
Google's [current Gemini API billing guidance](https://ai.google.dev/gemini-api/docs/billing)
states that Cloud Welcome/free-trial credits should not be assumed usable for
Gemini API or AI Studio usage. Preflight deliberately does not query private
Prepay balance/transaction details, and the optional Cloud Billing REST API is
disabled, so the artifact marks that billing-link check as a warning rather
than enabling another API. No model prompt, deployment, or other
credit-consuming operation has been performed.
