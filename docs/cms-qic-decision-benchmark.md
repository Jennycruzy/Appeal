# CMS QIC decision-summary benchmark

## Decision

Use the official Centers for Medicare & Medicaid Services (CMS) Qualified
Independent Contractor (QIC) Decision Search API as the primary public source
for the `regulator_outcome_benchmark` track. This removes the dependency on a
state-agency reply for the regulator-summary portion of the build.

The source is real regulator data, not Synthea and not a third-party mirror.
At the 2026-08-28 inspection it reported 901,471 Part C records and 240,958
Part D records. The aggregate-only inspection and the exact dataset identifiers
are recorded in
[`evidence/cms-qic-decision-search.json`](../evidence/cms-qic-decision-search.json).

The CMS landing page is
<https://www.cms.gov/medicare/appeals-grievances/appeals-decision-search-part-c-d>.
The machine-readable catalog is
<https://qic.cms.gov/api/1/metastore/schemas/dataset/items> and the API root is
<https://qic.cms.gov/api/1>.

## What the API supplies

| API field | Benchmark field | Decision |
| --- | --- | --- |
| `decision` | `regulator_outcome` | Use as the explicit QIC decision label. |
| `appeal_type` | `appeal_type` | Use directly; it is an explicit source field. |
| `decision_rationale` | `decision_rationale` / denial context | Preserve as a QIC-authored summary; never rename it to the original denial reason. |
| `coverage_rules` | `policy_context` | Preserve as summarized coverage rules, not as proof of the plan policy version. |
| `_condition` | `condition` | Use as source-provided condition text. |
| `item_service` or `drug` | `requested_item_or_drug` | Use the Part C or Part D field respectively. |
| `decision_date` | `regulator_decision_date` | Use as the source decision date. |
| no source field | `denial_reason` | Keep nullable. A QIC summary of a plan denial is not the plan's original denial-reason field. |
| no source field | `clinical_evidence` | Keep unavailable. Do not join a QIC row to a synthetic patient. |
| no source field | `prior_authorization` | Keep nullable and require row-level documentation before labeling. |

Part C and Part D are separate datasets. The inspector confirms their expected
schemas independently and fails if an expected field disappears. The query
template uses the dataset identifier and `offset`/`limit` pagination; the API's
reported count is not an artificial sample size.

## Privacy, reuse, and storage boundary

CMS describes the Part C source as decision summaries that may omit details to
protect the privacy of the parties. The inspector reads only a small bounded
sample, records aggregate pattern counts, and writes no case value or source
row to Git. The catalog currently exposes a USA.gov public-domain label. That
is recorded as source metadata, not as a legal privacy opinion.

The repository may contain the source metadata, schema, counts, field policy,
and aggregate evaluation evidence. Raw API rows and derived narrative rows
remain outside Git. A local extraction must be explicitly selected, stored
outside the repository, and hashed without copying its values into a report.

Run the metadata inspection with the public ACA value shown by the CMS page:

```text
APPEAL_CMS_QIC_ACA='<public ACA value>' make inspect-cms-qic
```

The command does not invoke a model, upload data to Google Cloud, or download
the bulk CSV. It reads the catalog and three-row schema/privacy samples from
each dataset. The public API key is not written to the output.

To extract the complete current Part D or Part C API result set for a local
summary run, use the paginated extractor. Both output paths must remain outside
the repository; the command refuses to overwrite an existing file:

```text
CMS_QIC_ACA='<public ACA value>' \
CMS_QIC_PART=part_d \
CMS_QIC_LOCAL_OUTPUT=../Downloads/cms-qic-part-d-summary.jsonl \
CMS_QIC_LOCAL_MANIFEST=../Downloads/cms-qic-part-d-summary.manifest.json \
make fetch-cms-qic-summary
```

The extractor uses atomic staging, checks the API-reported total, detects a
changing count or short page, hashes each source row/reference, and writes no
case values to stdout or the repository. It stops on identifier-shaped values
unless `--allow-privacy-shaped-values` is explicitly selected and a separate
human review is recorded. A bounded test can use `--max-records` directly with
`scripts/fetch_cms_qic_summary.py`; `--all` has no artificial corpus limit.

After an outside-repository extraction, run the summary adapter preflight:

```text
make run-cms-qic-summary \
  CMS_QIC_LOCAL_OUTPUT=../Downloads/cms-qic-part-d-summary.jsonl \
  CMS_QIC_LOCAL_MANIFEST=../Downloads/cms-qic-part-d-summary.manifest.json
```

The aggregate report is `evidence/cms-qic-summary-evaluation.json`. It counts
explicit source outcomes and appeal types, exercises the real case state
machine, and records an abstention for each row because the CMS summary does
not contain the original plan denial, complete clinical evidence, or original
plan-policy version. It must not be read as a full Appeal score.

The checked-in report is a three-row live smoke run. It proves the adapter
boundary against current source data; it is not an artificial corpus limit.
Use `--all` with the extractor when the complete current Part C or Part D
summary scope is selected for local processing.

The full Part D extraction attempt stopped on a privacy-shaped value before
acceptance. To locate every technical candidate without writing source rows,
run the full-scope scanner first:

```text
make scan-cms-qic-privacy \
  CMS_QIC_PART=part_d \
  CMS_QIC_PRIVACY_SCAN_REPORT=evidence/cms-qic-part-d-privacy-scan.json
```

The scanner stores only source offsets, field names, categories, value hashes,
and row/reference hashes. A report with candidates requires an authorized
human review before rerunning extraction with `--allow-privacy-shaped-values`.
That override is never implicit and does not itself clear privacy or reuse.

The live API accepted 1,000-row pages during the source check but rejected
larger 5,000- and 10,000-row requests with HTTP 400. Keep the page size at
1,000 unless a later API check establishes a new server limit.

## What this unlocks

This source is accepted for local regulator-summary benchmarking. It supports
real comparisons of a selected Appeal output to an explicit QIC decision and
to the QIC's rationale/policy-summary fields after a source adapter is run.
It also resolves the specific NY DFS problem: the application can use an
officially supplied `appeal_type` field without equating `Denial Reason` to it.

It does not unlock the `full_appeal_case_corpus` track. The public API does not
provide, in one package, the original denial letter, the complete clinical
evidence, the internal appeal submission/decision, or the original plan-policy
version. Therefore the project must still report zero full-case Appeal
evaluations until an authorized complete package is supplied.

## Next implementation boundary

1. Use `scripts/fetch_cms_qic_summary.py` to create the local-only paginated
   normalized input and preserve its outside-repository manifest.
2. Filter only by explicit source fields; do not infer prior authorization or
   manufacture `denial_reason`.
3. Run the existing Appeal state machine only when the selected row has the
   clinical, policy, and denial inputs that its Evidence Floor requires.
4. Record separate regulator-summary comparisons and full-case counts. A
   QIC summary row that abstains for missing clinical evidence is a valid
   fail-closed result, not a synthetic case and not an Appeal score.
