# Appeal

Appeal is a policy-grounded denial-appeal workflow with explicit evidence,
human-signature, deadline, and audit controls.

## Reviewer status

The project has two separate real-data release tracks. The repository does
**not** claim a completed full-case Appeal evaluation.

1. The **regulator-outcome benchmark** measures against real regulator
   determinations and regulator-authored summary findings. Its authoritative
   acceptance record is
   [`evidence/cms-qic-decision-search.json`](evidence/cms-qic-decision-search.json).
2. The **full Appeal case corpus** requires the original denial, policy
   criteria, clinical evidence, internal appeal, external-review rationale,
   and final outcome in one de-identified case package. Its acquisition and
   acceptance boundary are recorded in
   [`docs/full-appeal-corpus-acquisition.md`](docs/full-appeal-corpus-acquisition.md)
   and [`evidence/full-appeal-case-corpus-acceptance.json`](evidence/full-appeal-case-corpus-acceptance.json).

The primary public source selected for the regulator-summary benchmark is now
the official CMS Qualified Independent Contractor (QIC) Decision Search API.
At the latest inspection it reported 901,471 Part C records and 240,958 Part D
records, with explicit `decision`, `appeal_type`, `decision_rationale`,
`coverage_rules`, condition, requested item/service or drug, and decision-date
fields. Its metadata, live counts, schema checks, and field policy are in
[`evidence/cms-qic-decision-search.json`](evidence/cms-qic-decision-search.json)
and the implementation boundary is in
[`docs/cms-qic-decision-benchmark.md`](docs/cms-qic-decision-benchmark.md).
This is a real regulator-authored decision-summary source and is not a full raw
clinical case package: the original denial letter, complete clinical evidence,
internal appeal, and original plan-policy version are not exposed in the API.
The project therefore accepts it for regulator-summary benchmarking while
keeping full-case Appeal evaluations at zero.

The official DMHC download and API are currently returning Cloudflare 403
responses, so DMHC remains a secondary candidate rather than the current
benchmark source.
A public Kaggle mirror was therefore downloaded outside the repository and
inspected as a fallback candidate: 19,245 rows, 11 columns, `Determination`,
`Findings`, treatment categories, and `Reference ID`. It has no explicit
`Denial Reason` field and its technical scan found 22 physical-address-shaped
values. It is a candidate for the regulator-outcome track only and remains
pending provenance, privacy, reuse, and prior-authorization review. The
metadata-only record is
[`evidence/dmhc-kaggle-acquisition.json`](evidence/dmhc-kaggle-acquisition.json).

Two other manually acquired regulator candidates are also tracked locally:

- The NY DFS all-years export is preserved unchanged and local-only.
- It contains 61,606 observed rows, an `Appeal Decision` outcome, and a
  `Denial Reason` column.
- The archive UI exposes an `Appeal Type` filter, but the export has no
  `Appeal Type` column. That mapping is unresolved and is not inferred.
- Oregon's official IRO Case Detail Report is also preserved unchanged and
  local-only. It contains 2,230 observed case rows, an explicit `Case Outcome`,
  review type/category fields, and a treatment field. The project owner has
  authorized local-only use of all 1,640 completed-review outcome rows based on
  the official public download; no redistribution or prior-authorization claim
  is made.
- NY privacy/mapping/reuse review remains unresolved. Oregon is accepted only
  for local external-review outcome evaluation. The fail-closed adapter
  preflight has run across all 1,640 accepted rows and abstained before denial
  parsing because the source does not provide denial text, policy references,
  or clinical evidence. Full Appeal evaluations and regulator-ground-truth
  comparisons remain **zero**.
- A published DMHC case example is a discovery lead only; it is not an official
  payload import, accepted corpus row, or evaluation result. California DWC was
  investigated separately and rejected as a primary benchmark because it is a
  workers' compensation source and its public index does not provide the
  complete denial packet needed here.

Start with the [release-track handoff](docs/HANDOFF.md#release-tracks-2026-08-28),
the [CMS QIC benchmark record](docs/cms-qic-decision-benchmark.md),
then the [NY DFS handoff](docs/HANDOFF.md#ny-dfs-schema-mismatch--resume-here),
the [Oregon fallback](docs/HANDOFF.md#oregon-iro-case-detail-fallback), the
[NY acceptance manifest](evidence/ny-dfs-acceptance.json), the [Oregon
acceptance manifest](evidence/oregon-acceptance.json), and the review-request
record for [NY DFS](docs/ny-dfs-review-request.md) plus the optional Oregon
follow-up [request](docs/oregon-iro-review-request.md).

## What is and is not evidence

The Synthea/HAPI material is a reproducible integration fixture and data-plane
check. It is not real-denial evidence and does not support a clinical or
regulator-ground-truth claim. The CMS QIC API is the accepted public source for
regulator-authored decision-summary benchmarking; it does not supply the
clinical Evidence Floor required for a full Appeal run. The Oregon source-specific gate permits a
local-only adapter preflight and outcome-label inventory; it does not yet
support a full denial appeal evaluation. The NY source remains separately
blocked.

All corpus gates are fail-closed within their respective tracks. CMS API rows,
the raw NY DFS and Oregon files, and the DMHC mirror
are not committed. The local Oregon evaluation input and DMHC mirror CSV stay
outside the repository; repository evidence contains metadata and aggregate
counts only—not case numbers, treatment strings, or narrative values. The CMS
inspector likewise writes no source row values.

## Google Cloud status

The workspace has Google Cloud project and API-registration evidence, but no
application has been deployed. There is no repository evidence of a Cloud Run
service, Cloud Storage bucket, database, Artifact Registry image, or uploaded
real-case data. The local `gcloud` profile currently has no active project or
account; the prior ADC and preflight records are configuration evidence, not a
hosted application. See the [cloud handoff](docs/HANDOFF.md#google-cloud-hosting-status).

## Verification

```text
make test
make typecheck
make validate-ny-dfs
APPEAL_CMS_QIC_ACA='<public ACA value>' make inspect-cms-qic
make inspect-dmhc-imr \
  DMHC_IMR_INPUT=../Downloads/independent-medical-review-determinations-trends.csv
make inspect-oregon-iro \
  OREGON_IRO_INPUT=../Downloads/oregon-iro-case-detail-report.xlsx
make prepare-oregon-local-evaluation \
  OREGON_IRO_INPUT=../Downloads/oregon-iro-case-detail-report.xlsx \
  OREGON_IRO_LOCAL_OUTPUT=../Downloads/oregon-iro-local-evaluation.json
make run-oregon-local-evaluation \
  OREGON_IRO_LOCAL_OUTPUT=../Downloads/oregon-iro-local-evaluation.json
```

The Oregon run writes aggregate-only evidence to
`evidence/oregon-evaluation.json`. Its current result is an adapter preflight
with 1,640 explicit abstentions, not an Appeal score.

To create the local privacy-review packet, use the unchanged workbook and an
output path outside this repository:

```text
make prepare-ny-dfs-review \
  NY_DFS_INPUT=../Downloads/peasadata.xlsx \
  NY_DFS_PRIVACY_REVIEW=../Downloads/ny-dfs-privacy-review.json
```

Then run `make review-ny-dfs-privacy`. The reviewer sees candidate values only
in the terminal; the saved decision file contains hashes and decisions only.
Hash that decision file and record the hash in the acceptance manifest after
the review is complete.
