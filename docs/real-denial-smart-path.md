# Real-denial acquisition path

Updated: 2026-08-28

The project uses two explicit real-data lanes. The public lane can begin now;
the complete-case lane needs controlled access. They must not be merged or
described as the same evidence.

## Lane A — regulator-outcome benchmark

Use the official CMS Qualified Independent Contractor (QIC) Decision Search API
as the immediate structured source. It contains real Part C and Part D QIC
decision summaries with explicit decision, appeal type, rationale, coverage
rules, condition, requested item or drug, and date fields. The source is already
accepted for summary benchmarking in
[`evidence/cms-qic-decision-search.json`](../evidence/cms-qic-decision-search.json).

The CMS extractor pages the API into a local-only normalized file outside Git.
It keeps `appeal_type` and `regulator_outcome` from explicit source fields and
leaves `denial_reason`, `clinical_evidence`, and `prior_authorization` null
unless a row supplies those facts. A CMS summary may be compared with a
summary-level Appeal output, but it cannot be turned into a full clinical case
or joined to Synthea.

Washington is the next public-source check. The Washington Office of the
Insurance Commissioner currently advertises a public search for independent
review decisions by company, diagnosis, treatment, decision, and reason. The
official candidate record is
[`evidence/wa-oic-iro-search.json`](../evidence/wa-oic-iro-search.json).
The older search URL printed in an agency guide currently renders a producer,
agency, and company lookup page, so it is not treated as the current IRO API or
export endpoint. We will resolve the current search link, capture one bounded
redacted result, inspect its actual fields, and review terms before accepting
any row.

NY DFS, DMHC, Oregon, and Michigan remain separate source-specific candidates.
Their existing privacy, reuse, provenance, and field-mapping decisions are not
overridden by CMS or Washington.

## Lane B — complete Appeal case corpus

No public source verified so far provides the entire package in one reusable
corpus: original denial, denial reason, policy version, clinical evidence,
internal appeal, external review, and final outcome. Public regulator summaries
are real, but they normally omit at least the raw clinical record and the
original plan-policy version.

The complete-case route is therefore an authorized data partnership with a
payer, IRO, third-party administrator, academic medical center, or
quality-improvement program. A second valid route is a patient-consented case
collection. Both routes can produce real cases; neither requires treating an
unanswered public-agency email as permission.

The minimum partner delivery is defined in
[`full-appeal-corpus-acquisition.md`](full-appeal-corpus-acquisition.md). It
must include a stable de-identified case ID, original denial or structured
equivalent, policy criteria/version, clinical evidence used by the reviewer,
internal appeal, external review, outcome, and explicit prior-authorization
status or `not_applicable`.

## Execution order

1. Run the full-scope CMS privacy scan before extraction. If it finds
   candidates, complete human review before allowing narrative extraction.
2. Extract the selected CMS Part C or Part D scope outside the repository and
   retain its source manifest and file hash.
3. Run the CMS summary adapter preflight. Record explicit source outcomes,
   summary-field presence, and abstentions separately from full Appeal
   evaluations.
4. Resolve and inspect the current Washington IRO search endpoint. Accept it
   only after actual schema, privacy, provenance, and reuse checks pass.
5. Procure one complete-case delivery under a written data-use or equivalent
   authorization, or collect patient-consented packets under documented
   consent and redaction controls.
6. Complete the human acceptance manifest before running the full Appeal
   evaluator. Until then, full-case evaluations and end-to-end regulator
   comparisons remain zero.

## Non-negotiable boundary

“Real” means the record originated from an actual denial or external-review
process. “Complete” means the required denial-to-outcome package is available
for the same de-identified case. A real regulator summary is valid evidence for
Lane A, but it is not evidence that Lane B is complete.
