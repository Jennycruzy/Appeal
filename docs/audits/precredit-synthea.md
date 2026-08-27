# Pre-credit Synthea audit

Audit date: 2026-08-27

This is local, no-billing work. The synthetic corpus and local HAPI data-plane
checks were completed on 2026-08-27. It does not clear the blocked cloud
discovery requirements or establish a real-denial evaluation corpus.

## Completed evidence

- `config/requirements.json` pins Synthea `v4.0.0`, release commit `0185c09`,
  the `synthea-with-dependencies.jar` asset, its SHA-256
  `ed43c20ad40ba5c3bc724503a5af032715fe3c491620b766148e7c2361e6ecc1`, Java
  major version 17, population 300, California geography, patient seed
  `24082501`, clinician/provider seed `24082502`, reference date `20260826`,
  end date `20260826`, and a one-thread pool for bounded reproducible runs.
- The pinned JAR was downloaded to `.cache/synthea/v4.0.0/` and verified with
  `shasum -a 256`. The raw JAR and all generated patient bundles are ignored by
  `.gitignore` and are not repository artifacts.
- The official Synthea release was run in the pinned `eclipse-temurin:17-jre`
  container. A historical default-geography run, before the California
  alignment, reported `Records: total=346, alive=300, dead=46`, `RNG=300`,
  and `Clinician RNG=5645`; it is not the current corpus proof.
- A bounded corrected California smoke run was executed twice with Docker
  limited to 2 GiB and one CPU, JVM heap limited to 1.4 GiB, and Synthea's
  thread pool set to one. Each run used five patients, both pinned seeds,
  `-r 20260826`, `-e 20260826`, and the positional `California` location; each
  completed with `Records: total=5, alive=5, dead=0`, `RNG=5`, and
  `Clinician RNG=34460`.
- The recorder compared the two smoke outputs and passed with five patient
  bundles, 17 resource types, and patient-bundle fingerprint
  `d2f26ad6ffb4b0238fea62d5e86bb2a8ccdf6246733a7c9f42250a71d8f67215`.
  Its comparison was `identical=true`, with no changed, missing, or extra
  patient bundle files. This is recorded in
  `evidence/synthea-smoke.json`.
- Two measured fixed-end runs at each of 25, 100, and 300 requested patients
  passed the recorder comparison. The full run produced 342 patient bundles,
  20 resource types, and about 1.1 GiB of ignored local output. The authoritative
  aggregate counts, tracked hashes, and full comparison are recorded in
  `evidence/corpus.json`.
- The exact 342-bundle manifest set was loaded into pinned HAPI FHIR R4 using
  the default in-memory H2 database and a 5 GiB JVM heap. All 342 transaction
  POSTs returned HTTP 200; the load report is `evidence/hapi-load-full.json`.
- `make verify-hapi` passed with exact matches for all 20 source resource types.
  HAPI created 830 server-side `Practitioner` placeholder resources for
  unresolved references; the verifier records them as unexpected without
  treating them as source corpus resources.
- A follow-up restart test against a file-backed H2 variant failed with
  `Chunk 15190 not found`; file-backed H2 persistence is therefore not part of
  the accepted setup. Recreate a fresh HAPI instance for another verified load.
- `make inspect-synthea` passed against the manifest-tracked hashes. Its
  aggregate-only report is `evidence/synthea-distribution.json`; it describes
  chart evidence availability and explicitly does not establish policy
  criterion sufficiency.

## Reproducibility finding

The first repeated run used fixed `-s 24082501`, `-cs 24082502`, and
`-r 20260826` but omitted `-e`. The recorder correctly failed the comparison.
It found wall-clock differences in Synthea's timestamped hospital/practitioner
metadata filenames and in active encounter, Claim, and ExplanationOfBenefit
dates. The failed comparison is evidence of a real defect in the invocation,
not a passing determinism result.

The cause is confirmed in Synthea's official CLI source: `-r` assigns the
reference time, while `-e` independently assigns the simulation end time. When
`-e` is omitted, the end time remains the process wall clock. The same source
documents the separate clinician seed option `-cs`:
<https://raw.githubusercontent.com/synthetichealth/synthea/master/src/main/java/App.java>.

The invocation was corrected to include `-e 20260826`, use one generator thread,
and fingerprint only patient FHIR bundles rather than Synthea's timestamped
organization/practitioner metadata. The first full-scale attempt with that
correction was stopped during module startup because it consumed too much Mac
memory. The bounded 25-, 100-, and 300-patient runs then completed twice at
each scale and passed the patient-bundle comparison. The final manifest is
`evidence/corpus.json`.

The fix is therefore specific and testable: run the same JAR with `-s`, `-cs`,
`-r`, `-e`, and the configured thread-pool setting twice, then require the
recorder's `regeneration_comparison.identical` result to be true.

The first full-scale attempt at that corrected command was stopped during
module startup after it began consuming too much Mac memory. Its ignored output
directory was about 6.2 MB with four non-patient JSON files and no patient
bundle. This is an operational resource finding, not a reproducibility result.
The measured bounded runs show that the fixed-end inputs work under a 2 GiB
container limit. The 300-patient proof, HAPI import, aggregate verification,
and evidence distribution review are complete; policy mapping and real-denial
evaluation remain separate gates.

## Bounded smoke verification

The following command was run into `smoke_california_fixed_a` and then repeated
unchanged into `smoke_california_fixed_b`:

```text
docker run --rm --pull=never --memory=2g --memory-swap=2g --cpus=1 \
  -e JAVA_TOOL_OPTIONS=-Xmx1400m \
  -v /Users/user/appeal/.cache/synthea/v4.0.0:/data \
  eclipse-temurin:17-jre java -jar /data/synthea-with-dependencies.jar \
  -s 24082501 -cs 24082502 -p 5 -r 20260826 -e 20260826 \
  --generate.thread_pool_size=1 \
  --exporter.baseDirectory=/data/smoke_california_fixed_a \
  --exporter.fhir.export=true California
```

The second run changed only the output directory to
`smoke_california_fixed_b`. Both runs
completed successfully. The recorder output was:

```text
patient_bundle_count=5
bundle_set_fingerprint=d2f26ad6ffb4b0238fea62d5e86bb2a8ccdf6246733a7c9f42250a71d8f67215
resource_types=17
regeneration_comparison={'changed_files': [], 'extra_in_second': [], 'identical': True, 'missing_from_second': []}
```

This is a patient-bundle byte comparison at smoke scale. It intentionally does
not claim that Synthea's runtime-timestamped hospital/practitioner metadata is
byte-identical. Appeal's clinical corpus fingerprint is defined over patient
FHIR bundles, and the final manifest must preserve that scope explicitly.

## Remaining data-plane gap

The aggregate report describes what FHIR evidence types are available, but no
policy document has yet been selected and human-validated against those types.
The report must not be read as proof that any individual policy criterion is
satisfied.

## Blockers

- At the time of this 2026-08-26 pre-credit audit, cloud billing was disabled,
  so Gemini model discovery and managed Agent Platform probes were blocked.
  The current project state is recorded in the 2026-08-27 addendum in
  `docs/audits/phase-0.md`.
- The official DMHC IMR data endpoints returned HTTP 403 to the fail-closed
  fetcher. A separate Oregon external-review outcome subset is accepted for
  local-only use; its adapter preflight abstained on all rows before denial
  parsing, and it is not a prior-authorization corpus.

## Reproducible HAPI verification

With an empty in-memory HAPI container running, load the exact patient-bundle
set from the full manifest and then verify aggregate resource counts:

```text
make load-hapi
make verify-hapi
make inspect-synthea
```

The loader must use the 342 tracked patient bundles from `evidence/corpus.json`;
the reports must contain aggregate results only. Do not replay POST bundles
against a populated database or after a restart; use the loader's explicit
`HAPI_START_INDEX` only after reconciling the HAPI count in the same live
process.

## Exit status

The Synthea asset is pinned, and the corrected fixed-end invocation has passed
two-run patient-bundle comparison at full requested population. The corpus
manifest is complete; the exact corpus was loaded and verified in a live local
HAPI session, and its aggregate evidence distribution is recorded. Real-denial
evaluation, policy terms, and cloud-dependent work remain incomplete.
