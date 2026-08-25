# Phase 0 self-audit — discovery baseline

Status: blocked; Phase 1 must not start.

Audit date: 2026-08-25

The live command used for this audit was:

```text
GOOGLE_CLOUD_PROJECT=jennycruzy-53677 python3.12 scripts/preflight.py
```

The command completed with exit code `2`, which is the script's explicit
fail-closed result when blockers remain. It wrote
[`docs/preflight.json`](../preflight.json), generated at
`2026-08-25T05:34:42.045063Z` in the final run. The artifact SHA-256 printed
by the final run was
`8394c802759ca009869277e528652c4a6da5fb8f4fb6bf4ca77092c1cc0decbc`.

The final run reported:

```text
Blockers: 4
BLOCKER: Gemini model discovery
BLOCKER: Region and residency
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
  `Gemini model discovery` is blocked because the project region is not
  configured and `aiplatform.googleapis.com` is not enabled in the selected
  project. No model string was guessed.
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

The authenticated user can see two active Google Cloud projects:

```text
jenny-wallet-guard  (950457737025)
jennycruzy-53677    (346649480730)
```

`jennycruzy-53677` was used provisionally for read-only discovery because it
has the general project name. This choice is not final and no Google Cloud
resource was created or changed by this build. Its live Service Usage listing
reported 39 enabled services, including Cloud Resource Manager, Cloud Trace,
Datastore, Pub/Sub, Logging, Monitoring, and Cloud SQL support. Vertex AI was
not in the enabled-service list, so model discovery could not proceed.

The Mac has Google Cloud CLI `581.0.0` and a user ADC credential. The ADC quota
project was set locally to `jennycruzy-53677`; this changed only the local ADC
configuration. No service-account key was created or stored.

## Gaps

- The project target needs explicit confirmation before enabling
  `aiplatform.googleapis.com` or any paid/managed service.
- A region is not selected. It must be chosen from the live model/location
  surface after Vertex AI access is available; the source code must not infer
  one from geography or memory.
- Managed Agent Platform component endpoints and residency metadata are not
  yet available through an authenticated probe in this project.
- Quota-metric probing needs the current live service bindings and must be
  completed before deployment arithmetic is accepted.
- Aetna and Cigna policy sources are not ingestion candidates under the
  observed robots/terms responses. UHC remains pending human terms review.
- The public Synthea release endpoint initially exposed a moving
  `master-branch-latest` tag. The preflight was corrected to select a dated,
  non-prerelease release; the final evidence records `v4.0.0`.

## Blockers

1. Confirm whether `jennycruzy-53677` is the intended Appeal project or select
   `jenny-wallet-guard`.
2. After confirmation, enable and probe the live Vertex/Agent Platform surface
   using the current discovery document. Do not hardcode a model ID.
3. Select and record a region only after the live model listing proves the
   required Gemini version is available there.
4. Complete quota and residency probes, then rerun this audit artifact.
5. Obtain explicit terms permission or replace Aetna/Cigna with permitted
   policy sources before Phase 1 ingestion.

## Exit criteria

Phase 0 is not complete. The model ID, component availability, region,
quotas, and source permissions are not all verified. The build is therefore
stopped before Phase 1, as required by the specification.
