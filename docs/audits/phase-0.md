# Phase 0 self-audit — discovery baseline

Status: blocked; Phase 1 must not start.

Audit date: 2026-08-25

The live command used for this audit was:

```text
GOOGLE_CLOUD_PROJECT=appeal-fleet-2026-0825 APPEAL_GCP_REGION=europe-west2 python3.12 scripts/preflight.py
```

The command completed with exit code `2`, which is the script's explicit
fail-closed result when blockers remain. It wrote
[`docs/preflight.json`](../preflight.json), generated at
`2026-08-25T07:09:36.390843Z` in the final run. The artifact SHA-256 for this
run is
`650a61e5b0e6facfd69a0b00ed1f27a19ecba4b8f96a47a0ce5bb4a133c8ffdb`.

The final run reported:

```text
Blockers: 3
BLOCKER: Gemini model discovery
BLOCKER: Policy source: aetna_cpb
BLOCKER: Policy source: cigna_policy
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
  `docs/preflight.json` records robots and terms HTTP results for all three
  configured sources and `policy_fetch_performed: false` for each. Aetna and
  Cigna returned robots/terms responses that do not permit automated fetching;
  UHC robots permits the index path but still requires human terms review.
  No policy document was fetched.
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
  observed robots/terms responses. UHC remains pending human terms review.
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

## Exit criteria

Phase 0 is not complete. The model ID, component availability, region,
quotas, and source permissions are not all verified. The build is therefore
stopped before Phase 1, as required by the specification.
