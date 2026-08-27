# NY DFS external-appeal review request (sent; response pending)

Use the official NY DFS external-appeal questions route,
`externalappealquestions@dfs.ny.gov`, listed on the [NY State External Appeal
page](https://www.dfs.ny.gov/complaints/file_external_appeal). Do not attach
`peasadata.xlsx` or any case narrative. The request is for schema and reuse
clarification, not for a case-level disclosure.

Status: sent by the project owner; written response pending as of 2026-08-27.

## Questions to send

Suggested subject: `Request for schema mapping and permitted reuse — NY DFS
External Appeals export`

1. The archive UI exposes an `Appeal Type` filter, while the all-years Excel
   export contains `Denial Reason` and no `Appeal Type` column. Does the export
   field `Denial Reason` represent the same field and value domain as the
   archive's `Appeal Type` filter? If not, what export field or documented rule
   maps to `Appeal Type`?
2. Is there an authoritative data dictionary, export schema, or version note
   for this workbook? Please explain whether the rendered result count and the
   all-years workbook row count are expected to differ.
3. May the downloaded export be used for internal, non-commercial model
   evaluation of denial-language classification and regulator-outcome
   comparison? May sanitized derived records, aggregate metrics, or row-level
   evaluation results be retained or redistributed? If permission depends on
   fields, please specify the permitted and prohibited fields.
4. Does NY DFS provide an approved de-identification or redaction procedure for
   summary text containing possible addresses, date-of-birth labels, or member
   identifiers?

The official archive describes the material as closed external-appeal decisions
with summaries and outcomes, and its search UI advertises an `Appeal Type`
filter. Cite those official pages in the request rather than treating the
workbook's `Denial Reason` header as an equivalent field.

## Evidence to retain with the reply

Record the date, responder/office, response or document URL, and a local hash of
the response. Store only the minimum response text needed to support the
decision; do not add workbook rows, case numbers, or narrative values to the
repository.

Record the response hash in `gates.schema_mapping.mapping_evidence_sha256` and
`gates.reuse.permission_evidence_sha256` as applicable. Hash the completed local
privacy-decision file and record it in `gates.privacy.review_record_sha256`.

The acceptance manifest is
`evidence/ny-dfs-acceptance.json`. Its `schema_mapping`, `privacy`, `reuse`,
and `prior_authorization` gates must be updated explicitly after review. A
written answer that does not resolve the field mapping or reuse scope leaves
the corresponding gate blocked.
