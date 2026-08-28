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

## Acquisition routes

The complete-case track has two practical routes:

1. An authorized payer, independent review organization, third-party
   administrator, academic medical center, or quality-improvement program
   supplies a de-identified batch under a written data-use agreement or an
   equivalent written authorization.
2. A patient or authorized representative supplies a case packet under written
   consent, followed by documented redaction and human privacy review.

Public regulator searches and unanswered agency outreach are not prerequisites
for either route. They remain useful for the separate regulator-summary lane,
but public visibility alone does not establish permission to reuse narrative
case material.

## Suitable acquisition partners

Prioritize a partner that controls the original denial and appeal record and can
provide a de-identified batch under the controls above. The delivery may be
secure-file-transfer or an approved portal; it must not be sent through GitHub,
committed to the repository, or uploaded to Google Cloud before the acceptance
manifest approves that storage location.

The requested batch has no artificial row limit. The first delivery should be
large enough to expose field missingness and label variation; the evaluation
sample size is chosen after the data owner confirms the population and label
quality. A small pilot is acceptable only as an intake validation and does not
unlock the full-case claim until the required fields are present for the
accepted cases.

## Acceptance boundary

The authoritative manifest is
[`evidence/full-appeal-case-corpus-acceptance.json`](../evidence/full-appeal-case-corpus-acceptance.json).
Until it is accepted, Appeal may run against synthetic integration fixtures and
regulator-summary benchmarks, but the project must report zero full-case Appeal
evaluations and zero end-to-end regulator comparisons.
