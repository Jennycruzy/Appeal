# APPEAL build handoff

Updated: 2026-08-26

## Current state

The repository is on `main`, and the GitHub remote is configured as
`https://github.com/Jennycruzy/Appeal.git`. The existing commits have been
pushed to `origin/main`. The work intentionally remains stopped before the
cloud-dependent build because the Google Cloud project has no active billing
account and the live Gemini model probe returns
`PERMISSION_DENIED: BILLING_DISABLED`.

No real PHI, payer credential, member ID, or service-account key was used or
added to the repository. Raw synthetic FHIR output is kept only in the ignored
`.cache/synthea/` directory.

## Done and verified

- Live discovery scaffolding and the current blocked preflight artifact are in
  `scripts/preflight.py`, `docs/preflight.json`, and `docs/audits/phase-0.md`.
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
- Synthea v4.0.0, the JAR digest, both seeds, fixed dates, and the recorder are
  now pinned. A bounded five-patient fixed-end smoke run passed twice with an
  identical patient-bundle fingerprint. The full 300-patient manifest and
  comparison are still outstanding. Details are in
  `docs/audits/precredit-synthea.md` and `evidence/synthea-smoke.json`.

### Reproducibility investigation

The first failed comparison was diagnostic, not random. Synthea's official CLI
source shows that `-r` sets the simulation reference time while `-e` separately
sets the simulation end time. Omitting `-e` left the end time at the process
wall clock, which changed active encounter, Claim, and ExplanationOfBenefit
timestamps between runs. Synthea also emits hospital/practitioner metadata
filenames containing a runtime timestamp. See the
[official Synthea CLI source](https://raw.githubusercontent.com/synthetichealth/synthea/master/src/main/java/App.java),
especially the `-cs`, `-r`, and `-e` option handling.

The correction is to pin both seeds, `-r`, and `-e`, and to fingerprint only
patient FHIR bundles. A bounded five-patient smoke run using that invocation
completed twice with the same 64-character patient-bundle fingerprint. This
proves the corrected invocation at smoke scale; it does not prove the full
300-patient export is safe or reproducible yet. A prior full-scale attempt was
stopped because it was consuming too much Mac memory; it reached module
startup and emitted only a few small files, not a partial patient corpus. No
Docker container is currently running.

Smoke settings and result:

```text
Docker limit: 2 GiB memory, 1 CPU
JVM heap: -Xmx1400m
Synthea: v4.0.0, -s 24082501, -cs 24082502, -p 5,
         -r 20260826, -e 20260826, thread pool 1
Run A/B: 5 patient bundles each; resource types 17
Patient-bundle fingerprint: 66d5c5ed651c09c2f9ea33567d6774eeda194171002e230e6fe229de1f9f9caa
Recorder comparison: identical=true; changed_files=[]; missing_from_second=[]; extra_in_second=[]
```

The raw export directories can contain Synthea hospital/practitioner metadata
whose filenames include runtime timestamps. The recorder deliberately excludes
those metadata files and compares the patient FHIR bundle set, which is the
corpus consumed by Appeal. The full-scale run must use this same documented
scope and produce the final `evidence/corpus.json`.

The next attempt must first use a small fixed-date smoke run with bounded
threads/JVM memory, then scale only after its resource profile is understood.
The full population must not be restarted blindly.

## Still outstanding

1. Scale the corrected Synthea invocation from the passing five-patient smoke
   run, measure resource use, finish two full 300-patient runs, and produce
   `evidence/corpus.json` with a passing patient-bundle comparison.
2. Inspect the generated evidence distribution and then pin and run HAPI FHIR
   locally. Do not hand-edit patient records.
3. Resolve the DMHC access path or document an official browser/manual
   provenance path; inspect the unmodified case-level schema before claiming
   real regulator ground truth.
4. Complete policy terms review and ingest only permitted, ETag-backed policy
   documents. Extract traceable criterion trees and perform human validation.
5. Re-run cloud preflight after billing is active. Discover the model ID and
   all managed component availability; request Agent Gateway and Agent
   Policies access immediately if preview-gated.
6. Only after preflight exit: build the independent PAS payer, then the agent
   identities/tools, event spine, Memory Bank, governance boundary, Gemma,
   observability, console, evaluation, and seeded demo.
7. The Phase 9 real-denial run and mandatory human-choice stop have not happened.

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

Then complete the staged fixed-end corpus proof before starting HAPI FHIR. The
cloud blocker remains a real blocker; do not invent a Gemini model ID or claim
access to managed agent components while billing is disabled.
