# Appeal data provenance

**Status:** acquisition is frozen as of 2026-08-28. This document closes the
source-selection work for the current build. It records what is accepted,
what is intentionally limited, and what is not being pursued for this
deadline.

## Accepted inputs

### CMS QIC Appeals Decision Search

The official CMS Qualified Independent Contractor Decision Search is the
primary real-data source for the regulator-summary benchmark. The repository
records the source metadata, schema, counts, field policy, and acceptance
decision in:

- `evidence/cms-qic-decision-search.json`;
- `evidence/cms-qic-part-d-bulk-inspection.json`; and
- `evidence/cms-qic-part-d-bulk-acceptance.json`.

The public source exposes regulator-authored summaries and explicit outcomes,
including decision, appeal type, rationale, coverage-rule summary, condition,
requested item or drug, and decision date. It does not provide a complete
Appeal case package. In particular, it does not supply the original plan
denial, the complete clinical evidence, the internal appeal, or the original
plan-policy version. It is therefore accepted for regulator-summary
benchmarking only.

The pinned Part D bulk fallback contains 240,958 rows. The local accepted
summary subset retains 240,916 rows and excludes 42 rows under the explicit
workspace-owner policy. The bulk file has no source-native `record_number`;
the acceptance manifest uses the pinned file SHA-256 plus row SHA-256, with
occurrence disambiguation for duplicate content. The raw file remains outside
the repository.

### Synthea and HAPI

Synthea v4.0.0 and the HAPI FHIR R4 instance are accepted as synthetic clinical
fixtures and integration infrastructure. Their reproducibility, hashes, seeds,
and resource distributions are recorded in `evidence/synthea-smoke.json`,
`evidence/synthea-distribution.json`, and `evidence/corpus.json`.

They are not real denial evidence and do not provide regulator ground truth.
They may exercise the Evidence Miner and FHIR-shaped interfaces in local
scenarios, but a synthetic chart must never be joined to a CMS summary row and
described as a real appeal case.

### Policy sources

The repository records Aetna, Cigna, UnitedHealthcare, and CMS policy-source
candidates in `config/policy_sources.json`, together with their access and
terms boundaries. Published policy text may be used only when the selected
source and intended use are authorized and the criterion is stored with a
verbatim span, source hash, and effective-date context. No source terms or
automated-fetch authorization are being re-investigated in this build phase.

The criterion-tree implementation is ready for policy artifacts; a live
Gemini-derived criterion corpus and its hand-validation agreement rate remain
open product work and must not be implied by this provenance record.

## Evaluated but not accepted for the current build

### NY DFS external appeal archive

The official export is preserved outside the repository and its integrity is
recorded. It contains a denial-reason field, but the export does not contain
the archive's Appeal Type filter as a field. Privacy and reuse decisions are
also unresolved. It remains blocked in `evidence/ny-dfs-acceptance.json`.

### Oregon IRO Case Detail Report

The official workbook is accepted for a local-only external-review outcome
adapter. It does not contain the denial narrative, policy criteria, or
clinical evidence required for a full Appeal evaluation. The current adapter
preflight records abstentions rather than an Appeal score. See
`evidence/oregon-acceptance.json` and `evidence/oregon-evaluation.json`.

### California DMHC IMR source and Kaggle mirror

The official source path was unavailable during acquisition, and the public
Kaggle mirror cannot substitute for official-source reconciliation, privacy
review, and reuse review. The mirror remains a blocked candidate in
`evidence/dmhc-regulator-benchmark-acceptance.json` and
`evidence/dmhc-kaggle-acquisition.json`.

### Other discovery sources

Washington OIC, California DWC, Michigan PRIRA, and the related discovery
materials were not promoted into the accepted corpus. They do not provide the
complete, authorized case package needed for the full Appeal track. Their
current status remains in the existing evidence and handoff records.

## Full Appeal boundary

No source currently accepted by this repository supplies all of the following
in one authorized, de-identified package: original denial, applicable policy
version, clinical evidence, internal appeal, external review, and final
outcome. Therefore completed full Appeal evaluations remain **zero**. This is
an evaluation boundary, not a failure of the local workflow implementation.

No new source investigation is part of the remainder of this build. Open
questions are recorded as limitations and do not block construction of the
local product path.
