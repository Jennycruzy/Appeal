# Evaluation and human-review protocol

Appeal reports two different kinds of evidence:

1. The operating system is tested locally and hosted on Google Cloud with
   tenant isolation, durable state, event delivery, security inspection,
   human approval, and a single external mutation gate.
2. The reasoning system is evaluated against frozen source-backed labels. A
   workflow trace is not a quality label, and a source field copied directly
   into a prediction is not a reasoning score.

This document defines the current CMS QIC decision-summary benchmark and the
point at which its labels become eligible for a quality claim.

## Benchmark boundary

The pinned CMS Part D decision-summary file contains 240,958 source rows. The
accepted local-evaluation population excludes 42 rows under the repository's
privacy and reuse manifest. Appeal samples 300 accepted rows deterministically:

- 200 development rows for calibration and error analysis;
- 100 locked-test rows for the reported benchmark;
- stratification by the available Part D fields, decision year, and rationale
  completeness;
- case references and source hashes instead of source-native identifiers in
  committed reports;
- regulator outcome in a physically separate `hidden_labels` object, never in
  model input or reviewer queues.

This is a real regulator-summary benchmark. It is not a complete denial packet:
it does not establish clinical efficacy, evidence sufficiency for a patient, or
whether an appeal would prevail. Those claims require the authorized complete
denial program described in the first-prize execution plan.

The source and sample manifests are:

- [`evidence/cms-qic-part-d-bulk-acceptance.json`](../evidence/cms-qic-part-d-bulk-acceptance.json)
- [`evidence/cms-qic-part-d-benchmark-sample.json`](../evidence/cms-qic-part-d-benchmark-sample.json)
- [`evidence/cms-qic-benchmark-baselines.json`](../evidence/cms-qic-benchmark-baselines.json)

## Human gold-label protocol

The locked-test records are distributed in two independently ordered queues:

- `/Users/user/Downloads/cms-qic-annotation-reviewer-a.jsonl`
- `/Users/user/Downloads/cms-qic-annotation-reviewer-b.jsonl`

They are intentionally outside Git because they contain regulator narrative.
The committed queue manifest records their hashes and proves that both queues
contain the same 100 locked-test cases:

[`evidence/cms-qic-annotation-queues.json`](../evidence/cms-qic-annotation-queues.json)

For a guided terminal review that checkpoints only validated rows, run the
human annotator against one queue. Each reviewer uses a different queue and a
different identity:

```bash
PYTHONPATH=src python3.12 scripts/annotate_cms_qic_queue.py \
  --input ../Downloads/cms-qic-annotation-reviewer-a.jsonl \
  --output ../Downloads/cms-qic-annotation-reviewer-a-filled.jsonl \
  --manifest evidence/cms-qic-annotation-queues.json \
  --taxonomy config/cms_part_d_annotation_taxonomy.json \
  --queue-key reviewer_a \
  --reviewer-id reviewer-a \
  --reviewer-role "utilization review researcher"
```

The annotator displays the regulator text with character offsets, derives the
route from the frozen taxonomy, and writes a recoverable checkpoint after each
validated case. It never edits the source queue and never displays the hidden
outcome.

### Spreadsheet review for the full locked set

If a reviewer needs to work through all cases in one sitting, create the
reviewer-A sheet:

```bash
make create-cms-qic-review-sheet \
  CMS_QIC_REVIEW_SHEET=../Downloads/cms-qic-reviewer-a-review-sheet.csv
```

The sheet contains all 100 locked-test cases—the only rows used for the
reported quality benchmark. The 200 development rows remain in the original
queue for calibration and are carried through unchanged by the importer.

Each row has the full outcome-blinded regulator rationale and policy context,
protected source hashes, an assistant proposal, and editable reviewer fields.
The proposal is a review aid only. Inspect it against the visible text, edit
the `disposition`, `primary_category`, `secondary_categories`, `route`, and
source-span fields as needed, add a `review_note` when useful, and set
`human_reviewed` to `TRUE` after reviewing the row. Do not edit the protected
context or the `assistant_proposal_*` reference columns. The sheet contains no
regulator outcomes.

After saving the edited copy, convert it back into the queue:

```bash
make import-cms-qic-review-sheet \
  CMS_QIC_REVIEW_SHEET_EDITED=../Downloads/cms-qic-reviewer-a-review-sheet-edited.csv \
  CMS_QIC_FILLED_QUEUE_A=../Downloads/cms-qic-annotation-reviewer-a-filled.jsonl \
  CMS_QIC_REVIEWER_A_ID=reviewer-a \
  CMS_QIC_REVIEWER_A_ROLE="utilization review researcher"
```

The converter verifies all 100 case identities, source hashes, category-to-
route mappings, spans, and human-review flags. It records that reviewer A
reviewed an assistant-assisted starting proposal. Reviewer B must continue to
use queue B without seeing reviewer A's sheet or output; the two queues remain
separate for agreement and adjudication.

Each reviewer labels the principal issue described by the regulator rationale,
without seeing the hidden outcome. The frozen taxonomy is grounded in CMS
coverage-determination, exceptions, and reconsideration guidance:

[`config/cms_part_d_annotation_taxonomy.json`](../config/cms_part_d_annotation_taxonomy.json)

Required fields are:

- principal rationale category;
- optional secondary categories;
- route implied by the predeclared taxonomy mapping;
- exact rationale and/or policy source spans, represented by offsets and a
  source hash rather than copied prose;
- confidence from 1 to 5;
- explicit abstention when the summary cannot support a reliable category.

The importer rejects an annotation if it:

- contains an outcome or hidden-label field;
- uses an unsupported category or route;
- violates the frozen category-to-route mapping;
- cites a span outside the source bounds or with a mismatched hash;
- is authored under a model/agent identity;
- is partial, duplicated, or attached to the wrong case.

Agreement is stricter than category agreement. The two reviews must also agree
on secondary labels, route, disposition, and source spans before the result is
called consensus. Any disagreement requires a third human adjudicator who is
not either reviewer. The adjudication note is retained outside Git and only
its SHA-256 is emitted in the aggregate gold report.

Assistant proposals cannot become gold labels by themselves. A proposal may
be used as a starting point only when a named human reviewer inspects every
row, edits or accepts the fields, and the provenance is retained. The final
gold file still requires two distinct reviewer identities and adjudication of
every disagreement.

## Commands

Check progress without revealing labels or writing source narratives:

```bash
make validate-cms-qic-annotations \
  CMS_QIC_ANNOTATION_QUEUE_A=../Downloads/cms-qic-annotation-reviewer-a.jsonl \
  CMS_QIC_ANNOTATION_QUEUE_B=../Downloads/cms-qic-annotation-reviewer-b.jsonl \
  CMS_QIC_REVIEWER_A_ID=reviewer-a \
  CMS_QIC_REVIEWER_B_ID=reviewer-b
```

The current status is intentionally recorded as:

[`evidence/cms-qic-annotation-status.json`](../evidence/cms-qic-annotation-status.json)

It reports 0/100 locked-test labels in each queue and `gold_claim_allowed:
false`. This is the correct result until humans complete the reviews.

After both queues are completed, prepare a separate adjudication file only for
disagreements. Its rows have this shape:

```json
{
  "case_ref": "<64-character case hash>",
  "resolution": "adjudicated",
  "decision_note": "Short human explanation retained outside Git.",
  "annotation": {
    "disposition": "annotated",
    "primary_category": "prior_authorization",
    "secondary_categories": [],
    "route": "utilization_management_exception",
    "rationale_spans": [],
    "policy_spans": [],
    "confidence": 4
  }
}
```

Build the locked-test gold file with explicit human identities:

```bash
make import-cms-qic-annotations \
  CMS_QIC_ANNOTATION_QUEUE_A=../Downloads/cms-qic-annotation-reviewer-a-filled.jsonl \
  CMS_QIC_ANNOTATION_QUEUE_B=../Downloads/cms-qic-annotation-reviewer-b-filled.jsonl \
  CMS_QIC_REVIEWER_A_ID=reviewer-a \
  CMS_QIC_REVIEWER_A_ROLE="utilization review researcher" \
  CMS_QIC_REVIEWER_B_ID=reviewer-b \
  CMS_QIC_REVIEWER_B_ROLE="utilization review researcher" \
  CMS_QIC_ADJUDICATION=../Downloads/cms-qic-adjudication.jsonl \
  CMS_QIC_ADJUDICATOR_ID=reviewer-c \
  CMS_QIC_ADJUDICATOR_ROLE="utilization review professional" \
  CMS_QIC_GOLD_OUTPUT=../Downloads/cms-qic-locked-test-gold.jsonl \
  CMS_QIC_ANNOTATION_REPORT=evidence/cms-qic-gold-labels.json
```

The command refuses to overwrite a gold file, refuses queue drift, and fails
closed if a disagreement lacks adjudication. The gold JSONL stays outside the
repository; the aggregate report is safe to commit because it contains case
hashes, labels, span coordinates, and hashes but no source narrative.

## What can be reported

Before gold import, the repository may report:

- source acceptance and reproducible sampling;
- leakage audit and deterministic baselines;
- annotation queue integrity and review progress;
- workflow safety and operational measurements.

After successful import, it may additionally report rationale-category,
operational-route, abstention, and source-span agreement metrics on the 100
locked-test cases. Outcome prediction remains a separately stratified,
exploratory task because regulator rationale can contain semantic outcome cues.

No result from this benchmark should be described as a full Appeal clinical
evaluation until an authorized complete denial package has been acquired,
reconstructed under the documented provenance rules, and run blind through the
full criterion/evidence workflow.
