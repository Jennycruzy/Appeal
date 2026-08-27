# Appeal

Appeal is a policy-grounded denial-appeal workflow with explicit evidence,
human-signature, deadline, and audit controls.

## Reviewer status

The repository does **not** claim a completed real-case evaluation. The active
release gate is acceptance of a real regulator-denial corpus. Two primary
official regulator candidates are now tracked:

- The NY DFS all-years export is preserved unchanged and local-only.
- It contains 61,606 observed rows, an `Appeal Decision` outcome, and a
  `Denial Reason` column.
- The archive UI exposes an `Appeal Type` filter, but the export has no
  `Appeal Type` column. That mapping is unresolved and is not inferred.
- Oregon's official IRO Case Detail Report is also preserved unchanged and
  local-only. It contains 2,230 observed case rows, an explicit `Case Outcome`,
  review type/category fields, and a treatment field. Redacted case synopses
  are available by request, but reuse and synopsis access are not yet approved.
- Privacy review and reuse permission remain unresolved for both candidates;
  accepted records, Appeal evaluations, and regulator-ground-truth comparisons
  remain **zero**.

Start with the [NY DFS handoff](docs/HANDOFF.md#ny-dfs-schema-mismatch--resume-here),
the [Oregon fallback](docs/HANDOFF.md#oregon-iro-case-detail-fallback), the
[NY acceptance manifest](evidence/ny-dfs-acceptance.json), and the review-request
drafts for [NY DFS](docs/ny-dfs-review-request.md) and
[Oregon](docs/oregon-iro-review-request.md).

## What is and is not evidence

The Synthea/HAPI material is a reproducible integration fixture and data-plane
check. It is not real-denial evidence and does not support a clinical or
regulator-ground-truth claim. The real-denial gate must pass before any case is
run through Appeal.

All corpus gates are fail-closed. The raw NY DFS and Oregon workbooks are not
committed, and the repository evidence contains metadata and aggregate counts
only—not case numbers, treatment strings, or narrative values.

## Verification

```text
make test
make typecheck
make validate-ny-dfs
make inspect-oregon-iro \
  OREGON_IRO_INPUT=../Downloads/oregon-iro-case-detail-report.xlsx
```

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
