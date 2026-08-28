# Full Appeal case-corpus acquisition brief

The project has two separate real-data tracks. The official CMS QIC API now
provides the primary public regulator-summary benchmark, but its summaries do
not by themselves provide a complete denial-to-appeal case file. The DMHC, NY
DFS, Oregon, and Michigan material has the same boundary. This brief defines
the package required to unlock the full Appeal evaluation track; obtaining that
package is no longer a prerequisite for the CMS summary benchmark.

## Target data package

For each de-identified case, request:

- a stable case identifier;
- the original denial letter or a structured equivalent, including denial date,
  requested service, and the explicit denial reason;
- the policy, guideline, or medical-necessity criteria version used;
- the clinical evidence actually available to the reviewer;
- the internal appeal submission, decision, dates, and disposition;
- the external-review submission, rationale, final outcome, and outcome date;
- an explicit prior-authorization status or `not_applicable` value when the case
  was not a prior-authorization case.

There is no artificial row limit in this acceptance definition. The evaluation
protocol will determine the sample size after the data owner confirms the
available population and label quality.

## Required permission and handling evidence

The data owner must provide provenance, acquisition date, reuse permission or
data-use agreement, and a de-identification or redaction attestation. The
project must record a human privacy decision, field mappings, missingness,
artifact hashes, and local access/retention controls before any narrative case
is accepted.

Raw case material stays outside Git. It must not be uploaded to Google Cloud,
the repository, or a third-party dataset host until the data owner permits that
storage location and the project records the applicable controls.

## Suitable acquisition partners

Prioritize an authorized health plan, independent review organization, third-
party administrator, academic medical center, or quality-improvement program
that can provide de-identified cases under a written agreement. Public
regulator pages and published case examples are useful seed fixtures, but they
are not substitutes for this package.

## Acceptance boundary

The authoritative manifest is
[`evidence/full-appeal-case-corpus-acceptance.json`](../evidence/full-appeal-case-corpus-acceptance.json).
Until it is accepted, Appeal may run against synthetic integration fixtures and
regulator-summary benchmarks, but the project must report zero full-case Appeal
evaluations and zero end-to-end regulator comparisons.
