# Pre-credit Synthea audit

Audit date: 2026-08-26

This is local, no-billing work. It does not clear the blocked cloud discovery
requirements and it does not claim that the data-plane exit criteria are met.

## Completed evidence

- `config/requirements.json` pins Synthea `v4.0.0`, release commit `0185c09`,
  the `synthea-with-dependencies.jar` asset, its SHA-256
  `ed43c20ad40ba5c3bc724503a5af032715fe3c491620b766148e7c2361e6ecc1`, Java
  major version 17, population 300, patient seed `24082501`, clinician/provider
  seed `24082502`, reference date `20260826`, end date `20260826`, and a four
  thread pool.
- The pinned JAR was downloaded to `.cache/synthea/v4.0.0/` and verified with
  `shasum -a 256`. The raw JAR and all generated patient bundles are ignored by
  `.gitignore` and are not repository artifacts.
- The official Synthea release was run in the pinned `eclipse-temurin:17-jre`
  container. The completed run using fixed patient, clinician, and reference
  inputs reported `Records: total=346, alive=300, dead=46`, `RNG=300`, and
  `Clinician RNG=5645`.
- An independent local scan of an earlier completed output found 344 patient
  FHIR bundles and a broad set of FHIR resource types. The authoritative
  aggregate counts for the final fixed-end corpus are not committed yet; they
  must come from the successful recorder run below.

## Reproducibility finding

The first repeated run used fixed `-s 24082501`, `-cs 24082502`, and
`-r 20260826` but omitted `-e`. The recorder correctly failed the comparison.
It found wall-clock differences in Synthea's timestamped hospital/practitioner
metadata filenames and in active encounter, Claim, and ExplanationOfBenefit
dates. The failed comparison is evidence of a real defect in the invocation,
not a passing determinism result.

The invocation was corrected to include `-e 20260826`, and the recorder was
updated to fingerprint only patient FHIR bundles rather than Synthea's
timestamped organization/practitioner metadata. That corrected run was still
in progress when the work session was interrupted and its container was then
stopped. No fixed-end comparison has passed yet, and `evidence/corpus.json`
does not exist.

## Gaps

- The final fixed-end corpus manifest and byte-identical comparison are still
  outstanding.
- The raw output directory may contain a partial corrected run in the ignored
  local cache; it must not be treated as evidence without a successful recorder
  result.
- The generated corpus has not yet been inspected against the evidence types
  required by the selected real policy criteria.
- HAPI FHIR has not yet been pinned, started, or loaded with this corpus.

## Blockers

- Cloud billing is disabled, so Gemini model discovery and managed Agent
  Platform probes remain blocked as recorded in `docs/audits/phase-0.md`.
- The official DMHC IMR data endpoints returned HTTP 403 to the fail-closed
  fetcher. No real denial/outcome corpus has been accepted.

## Next reproducibility command

Run the exact pinned command twice into two new ignored directories, then run:

```text
python3.12 scripts/record_synthea_corpus.py \
  --input-dir .cache/synthea/v4.0.0/<first-fixed-end-output> \
  --compare-dir .cache/synthea/v4.0.0/<second-fixed-end-output> \
  --output evidence/corpus.json
```

The command must exit zero and report `regeneration_comparison.identical: true`
before the local corpus is considered reproducible.

## Exit status

The Synthea asset is pinned and a substantial synthetic corpus was generated,
but the fixed-end byte-identical proof and corpus manifest are incomplete.
The data-plane work must not be represented as complete.
