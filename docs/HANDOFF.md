# APPEAL build handoff

Updated: 2026-08-26

## Current state

The repository is on `main`. Local commits are present, but no Git remote is
configured, so nothing has been pushed yet. The work intentionally remains
stopped before the cloud-dependent build because the Google Cloud project has
no active billing account and the live Gemini model probe returns
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
  now pinned. A completed run produced 346 patient bundles, but the corrected
  fixed-end byte-identical comparison is not yet proven. Details are in
  `docs/audits/precredit-synthea.md`.

## Still outstanding

1. Finish two corrected fixed-end Synthea runs and produce
   `evidence/corpus.json` with a passing byte-identical comparison.
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

## Push setup

`git remote -v` currently prints nothing. Once the public repository URL is
known, add it and push the existing `main` branch:

```text
git remote add origin <public-repository-url>
git push -u origin main
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

Then complete the fixed-end corpus proof before starting HAPI FHIR. The cloud
blocker remains a real blocker; do not invent a Gemini model ID or claim access
to managed agent components while billing is disabled.
