# CMS legal-ground review guide

This guide governs the versioned `cms_part_d_legal_ground_v2` locked set. An
official QIC outcome and an inferred legal ground are separate targets:

| Track | Gold label | What it measures |
| --- | --- | --- |
| `regulator_outcome` | CMS `Decision` field | Agreement with the published QIC determination |
| `inferred_legal_ground` | Two independent human readings of the rationale, with adjudication when needed | Operative ground, material secondary issues, route, and holding span |

Neither is a complete Appeal evaluation. The CMS source is a regulator-authored
decision summary; it does not provide the original plan denial, complete
patient evidence, original plan-policy version, filed appeal, or clinical
appropriateness judgment.

## What to label

Read `decision_rationale` first and use `policy_context` as supporting context.
Label the ground that controls the holding—not the first issue mentioned, a
background fact, or stock closing language. The primary category drives the
route. Add a secondary category only when the summary decides another material
issue that changes the appeal argument, evidence request, or disposition.

| Category | Use when the holding turns on… | Common error to avoid |
| --- | --- | --- |
| `non_formulary_exception` | The requested drug is absent from the formulary and exception criteria control | Calling alternative-drug language `step_therapy` |
| `tiering_exception` | Lower cost sharing for a non-preferred drug | Calling it general reimbursement |
| `prior_authorization` | Satisfying, waiving, or failing prior authorization | Ignoring a separately decided secondary ground |
| `step_therapy` | A required sequence of on-formulary drugs | Treating non-formulary exception criteria as step therapy |
| `quantity_limit` | Quantity, dose, frequency, or safety-edit restriction | Letting a background quantity mention control |
| `medically_accepted_indication` | FDA labeling, compendia, or medically accepted indication rules | Using the reimbursement opener instead of the holding |
| `payment_or_cost_sharing` | Reimbursement, payment, copay, coinsurance, or enrollee cost sharing after coverage eligibility | Triggering on boilerplate that payment cannot be made under Part D |
| `coverage_exclusion` | Statutory/benefit exclusion such as bulk powder, compound, device, or weight-loss drug | Mislabeling the closing payment sentence |
| `part_b_part_d_coordination` | Part B, Part D, or another benefit bucket is responsible | Treating it as utilization management |
| `at_risk_drug_management` | An at-risk drug-management program determination | Treating ordinary controlled-substance limits as at-risk management |
| `procedural_or_jurisdictional` | Timeliness, representation, dismissal, jurisdiction, or another process rule | Replacing a substantive holding with procedure |
| `other_coverage_rule` | A supported coverage ground fits no more specific category | Guessing when the summary is incomplete |
| `insufficient_information` | The summary cannot support a reliable primary ground | Filling an empty/ambiguous rationale from boilerplate |

`insufficient_information` is an abstention and cannot be secondary. The route
must be the taxonomy-derived route, not a free-form choice.

## Operative holding spans

Select the shortest contiguous sentence or sentences in `decision_rationale`
that state why the decision was made. Do not select the “At issue is…” framing
sentence unless it is the only holding. Do not select generic regulatory
boilerplate or a conclusion merely because it states the outcome. Coordinates
are Python/Unicode `start:end` offsets; the importer checks bounds and hashes.

`policy_spans` are optional. Leave them blank when `policy_context` is generic,
repeated boilerplate, or misaligned with the rationale. An invented policy
alignment is worse than an honest empty policy span.

## Eligibility and privacy

Sampling happens only after excluding empty `Decision_Rationale`, empty
`Coverage_Rules`, all accepted technical privacy candidates, and likely
professional names near `prescriber`, `physician`, `doctor`, `provider`,
`clinician`, or `pharmacist`, including explicit `Dr.`/`Doctor` honorifics.
The name detector produces candidates, not identity decisions; each candidate
requires human privacy review. The written sample is re-audited and one
residual candidate fails the audit.

The two sheets contain the same locked cases in different orders, with no CMS
outcome and no assistant-proposal columns. A row is eligible for gold only when
the importer records direct human entry, the reviewer has read it, and both
independent queues agree or a third human adjudicates the disagreement. The
older assistant-prefilled sheet is retired and rejected by the importer.

## Run the current track

All narrative-bearing files stay outside Git:

```bash
make sample-cms-qic-legal-benchmark
make audit-cms-qic-legal-benchmark
make create-cms-qic-legal-annotation-queues
make create-cms-qic-legal-review-sheets
```

Reviewer A edits `../Downloads/cms-qic-legal-ground-reviewer-a.csv`; reviewer B
edits only the B sheet. Fill `disposition`, `primary_category`, comma-separated
`secondary_categories`, the derived `route`, `holding_spans`, optional
`policy_spans`, confidence 1–5, and `human_reviewed=TRUE`. Never edit protected
context or source hashes.

Import and validate independently:

```bash
make import-cms-qic-legal-reviewer-a
make import-cms-qic-legal-reviewer-b
make validate-cms-qic-legal-annotations
```

If reviewers disagree, create an outside-Git adjudication file only for those
case hashes. The adjudicator must be a third human reviewing the same blinded
text. Then run:

```bash
make import-cms-qic-legal-annotations \
  CMS_QIC_LEGAL_ADJUDICATION=../Downloads/cms-qic-legal-ground-adjudication-v2.jsonl \
  CMS_QIC_ADJUDICATOR_ID=reviewer-c \
  CMS_QIC_ADJUDICATOR_ROLE="utilization review professional"
```

The gold JSONL and queues remain outside Git; repository evidence contains only
hashes, counts, labels, coordinates, and aggregate scores.

## Reporting discipline

Report explicit CMS outcome metrics under `regulator_outcome`. Report primary,
secondary, route, and holding-span metrics under `inferred_legal_ground`. Never
merge denominators or describe either as clinical efficacy or proof that Appeal
would win an original patient appeal. A full Appeal score remains gated on an
authorized complete denial package and a blind run through the Evidence Floor.
