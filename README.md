# Appeal

Appeal is a policy-grounded denial-appeal workflow with explicit evidence,
human-signature, deadline, and audit controls.

## Reviewer status

The repository does **not** claim a completed real-case evaluation. The active
release gate is acceptance of a real regulator-denial corpus:

- The NY DFS all-years export is preserved unchanged and local-only.
- It contains 61,606 observed rows, an `Appeal Decision` outcome, and a
  `Denial Reason` column.
- The archive UI exposes an `Appeal Type` filter, but the export has no
  `Appeal Type` column. That mapping is unresolved and is not inferred.
- Privacy review and reuse permission are unresolved; accepted records,
  Appeal evaluations, and regulator-ground-truth comparisons remain **zero**.

Start with the [NY DFS handoff](docs/HANDOFF.md#ny-dfs-schema-mismatch--resume-here),
the [acceptance manifest](evidence/ny-dfs-acceptance.json), and the
[review-request draft](docs/ny-dfs-review-request.md).

## What is and is not evidence

The Synthea/HAPI material is a reproducible integration fixture and data-plane
check. It is not real-denial evidence and does not support a clinical or
regulator-ground-truth claim. The real-denial gate must pass before any case is
run through Appeal.

All corpus gates are fail-closed. The raw NY DFS workbook is not committed,
and the local review packet contains hashes and cell locators only—not case
numbers or narrative values.

## Verification

```text
make test
make typecheck
make validate-ny-dfs
```

To create the local privacy-review packet, use the unchanged workbook and an
output path outside this repository:

```text
make prepare-ny-dfs-review \
  NY_DFS_INPUT=../Downloads/peasadata.xlsx \
  NY_DFS_PRIVACY_REVIEW=../Downloads/ny-dfs-privacy-review.json
```
