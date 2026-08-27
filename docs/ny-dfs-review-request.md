# NY DFS external-appeal review request (draft)

Use the official NY DFS contact route for the external-appeal archive. Do not
attach `peasadata.xlsx` or any case narrative. The request is for schema and
reuse clarification, not for a case-level disclosure.

## Questions to send

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

## Evidence to retain with the reply

Record the date, responder/office, response or document URL, and a local hash of
the response. Store only the minimum response text needed to support the
decision; do not add workbook rows, case numbers, or narrative values to the
repository.

The acceptance manifest is
`evidence/ny-dfs-acceptance.json`. Its `schema_mapping`, `privacy`, `reuse`,
and `prior_authorization` gates must be updated explicitly after review. A
written answer that does not resolve the field mapping or reuse scope leaves
the corresponding gate blocked.
