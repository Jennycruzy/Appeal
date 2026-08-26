# Pre-credit Synthea audit

Audit date: 2026-08-26

This is local, no-billing work. It does not clear the blocked cloud discovery
requirements and it does not claim that the data-plane exit criteria are met.

## Completed evidence

- `config/requirements.json` pins Synthea `v4.0.0`, release commit `0185c09`,
  the `synthea-with-dependencies.jar` asset, its SHA-256
  `ed43c20ad40ba5c3bc724503a5af032715fe3c491620b766148e7c2361e6ecc1`, Java
  major version 17, population 300, California geography, patient seed
  `24082501`, clinician/provider seed `24082502`, reference date `20260826`,
  end date `20260826`, and a four thread pool.
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

The cause is confirmed in Synthea's official CLI source: `-r` assigns the
reference time, while `-e` independently assigns the simulation end time. When
`-e` is omitted, the end time remains the process wall clock. The same source
documents the separate clinician seed option `-cs`:
<https://raw.githubusercontent.com/synthetichealth/synthea/master/src/main/java/App.java>.

The invocation was corrected to include `-e 20260826`, and the recorder was
updated to fingerprint only patient FHIR bundles rather than Synthea's
timestamped organization/practitioner metadata. The first full-scale attempt
with that correction was stopped during module startup because it consumed too
much Mac memory. It did not produce a patient corpus. The bounded smoke run
then completed twice and passed the patient-bundle comparison, but
`evidence/corpus.json` does not exist because the full 300-patient proof is
still outstanding.

The fix is therefore specific and testable: run the same JAR with `-s`, `-cs`,
`-r`, `-e`, and the configured thread-pool setting twice, then require the
recorder's `regeneration_comparison.identical` result to be true.

The first full-scale attempt at that corrected command was stopped during
module startup after it began consuming too much Mac memory. Its ignored output
directory was about 6.2 MB with four non-patient JSON files and no patient
bundle. This is an operational resource finding, not a reproducibility result.
The bounded smoke run shows that the same fixed-end inputs work under a 2 GiB
container limit. The next safe step is a measured scale-up, such as 25 and then
100 patients under the same cap, before deciding whether the 300-patient run
needs a lower-memory export strategy.

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

## Gaps

- The final fixed-end corpus manifest and full 300-patient patient-bundle
  comparison are still outstanding; the smoke-scale comparison passed.
- The raw output directory contains only a stopped startup attempt in the
  ignored local cache; it must not be treated as evidence without a successful
  recorder result.
- The full export's Mac memory profile has not been measured at intermediate
  population sizes; the passing smoke limit is not evidence that 300 patients
  will fit under it.
- The generated corpus has not yet been inspected against the evidence types
  required by the selected real policy criteria.
- HAPI FHIR has not yet been pinned, started, or loaded with this corpus.

## Blockers

- Cloud billing is disabled, so Gemini model discovery and managed Agent
  Platform probes remain blocked as recorded in `docs/audits/phase-0.md`.
- The official DMHC IMR data endpoints returned HTTP 403 to the fail-closed
  fetcher. No real denial/outcome corpus has been accepted.

## Next reproducibility command

Scale the bounded command to an intermediate population, measure it, then run
the exact pinned command twice into two new ignored directories and run:

```text
python3.12 scripts/record_synthea_corpus.py \
  --input-dir .cache/synthea/v4.0.0/<first-fixed-end-output> \
  --compare-dir .cache/synthea/v4.0.0/<second-fixed-end-output> \
  --output evidence/corpus.json
```

The command must exit zero and report `regeneration_comparison.identical: true`
before the local corpus is considered reproducible. The smoke result is not a
substitute for the final 300-patient manifest.

## Exit status

The Synthea asset is pinned, and the corrected fixed-end invocation has passed
at bounded smoke scale. The full 300-patient byte-identical patient-bundle
proof and corpus manifest are incomplete. The data-plane work must not be
represented as complete.
