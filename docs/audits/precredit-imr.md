# Pre-credit real-corpus discovery

Audit date: 2026-08-27

This is a discovery record for the local, no-billing workstream. It does not
clear the blocked Phase 0 exit criteria and it does not claim that the Phase
1D evaluation corpus has been ingested.

## California DMHC IMR source

The intended real denial/outcome source is the California Department of Managed
Health Care's Independent Medical Review (IMR) material:

- [Data.gov catalogue record](https://catalog.data.gov/dataset/independent-medical-review-imr-determinations-trend)
- [California Open Data record](https://lab.data.ca.gov/dataset/independent-medical-review-imr-determinations-trend/1e9714f7-ad88-4d73-adb3-72bd65c8aa77)
- [DMHC IMR decisions page](https://dmhc.ca.gov/FileaComplaint/ConsumerIndependentMedicalReviewComplaint/IMRDecisions.aspx)
- [DMHC searchable IMR database](https://wpso.dmhc.ca.gov/imr/)
- [Official CSV resource](https://data.chhs.ca.gov/dataset/b79b3447-4c10-4ae6-84e2-1076f83bb24e/resource/3340c5d7-4054-4d03-90e0-5f44290ed095/download/independent-medical-review-imr-determinations-trends.csv)
- [Official data dictionary](https://data.chhs.ca.gov/dataset/b79b3447-4c10-4ae6-84e2-1076f83bb24e/resource/2c5c2144-138f-4feb-b2af-a1176995e1b1/download/imrdatadictionary.pdf)
- [Official archive resource](https://data.chhs.ca.gov/dataset/b79b3447-4c10-4ae6-84e2-1076f83bb24e/resource/9ab6e381-bef2-43dd-b096-efa85d93a804/download/independent-medical-review-imr-determinations-trend-wroodu9e.zip)

The catalogue metadata declares the source public and identifies a CC BY
licence. DMHC states that its IMR decision database contains decisions since
January 1, 2001. The current [CA Open Data record](https://lab.data.ca.gov/dataset/independent-medical-review-imr-determinations-trend)
was also reachable on 2026-08-27 and reported a 2001--current timeframe and a
2026-08-24 update. Those statements establish provenance and a licence lead;
they do not yet prove that the downloadable `Trend` resource contains every
case-level denial, policy, clinical, and determination field required by
Phase 1D.

## Retrieval result

The official catalogue and resource URLs were discovered, but the direct data
resource and datastore requests returned HTTP 403 to the local fetch client on
2026-08-25. The browser-accessible catalogue metadata was not treated as a
substitute for the data file. No IMR bytes were committed, transformed,
redistributed, or used as evaluation ground truth.

The repository now records the URLs and the fail-closed probe in
`config/real_corpus_sources.json` and `scripts/preflight.py`. The probe uses
`HEAD` and captures status, ETag, and content type; it does not download the
large data resources during preflight.

The first real fetcher checks were also run against external endpoints:

- `scripts/fetch_public_source.py --source-id california_dmhc_imr_determinations --resource csv_url` reached the official host and recorded HTTP 403; it created no payload.
- `scripts/fetch_public_source.py --source-id cms_0057_f_prior_authorization_metrics --resource template_url` received HTTP 200 but no ETag; it rejected the payload and created no cache entry.

Both outcomes are intentional. The repository will not treat a response as a
reproducible corpus artifact unless the response can be revalidated with an
ETag. The CMS page remains a verified definition source in preflight, but it is
not yet a cached benchmark artifact.

## Retrieval follow-up

The 403 is being treated as an access problem to resolve, not as evidence that
the DMHC corpus is unavailable. The following official routes were tested on
2026-08-26 and 2026-08-27:

- A plain GET of the official CSV returned HTTP 403.
- A GET with a current Safari User-Agent, Referer, Accept headers, and a 1 KB
  Range request also returned HTTP 403.
- The California Open Data datastore endpoint returned HTTP 403.
- The official Data.gov catalogue was inspected. Its harvested metadata exposes
  the same CSV, ZIP, and dictionary URLs on `data.chhs.ca.gov`; it does not
  provide a separate data mirror.
- The newer CA Open Data record at `lab.data.ca.gov` was reachable and exposed
  the official CSV preview/download links, but those links still resolve to
  `data.chhs.ca.gov`. No case rows were exposed by the retrieval client and no
  payload was saved.
- The DMHC searchable IMR database at `https://wpso.dmhc.ca.gov/imr/` returned
  HTTP 403 from the command-line client and timed out through the web retrieval
  client.
- The public portal page and direct CSV URL were opened in a normal Mac browser
  session. The browser displayed Access Denied and no file appeared in the
  Downloads directory.
- Socrata SODA URL shapes were tested diagnostically and returned HTTP 403. The
  official portal page exposes a CKAN/DKAN-style `data.ca.gov/api/3/action`
  datastore endpoint and UUID resource IDs, so no Socrata app token route has
  been established for this dataset. No token was created or stored.

The direct download response identifies Cloudflare and the protected host as
`ogopendata.com`. This explains the consistent 403 across the bulk file, API,
and searchable database routes. It is not a licence denial. The next permitted
access path is a manual download from a browser/network that passes the WAF, or
an official response from the DMHC Open Data contact at
`opendata@dmhc.ca.gov`. If a file is obtained, it must be kept unmodified,
hashed, and recorded with the original URL, retrieval date, and licence before
any analysis. Until then, the case-level corpus remains pending.

The published third-party [DMHC case example](https://meritsappeals.com/research/anatomy-of-an-appeal-that-won)
for case `MN22-37709` is useful as a field-shape and retrieval lead: it reports
a denial basis, treatment, clinical findings, and an overturned determination.
It is not an official payload, it has not been independently reconciled to the
DMHC export, and it is not accepted as a corpus row or evaluation result.

## Alternative regulator sources investigated

The DMHC access failure is being treated as an unresolved retrieval blocker, not
as permission to claim that the data was ingested. Separate public regulator
sources were investigated on 2026-08-27. None has been accepted into the
corpus yet.

### New York Department of Financial Services — primary fallback candidate

The [official External Appeals Searchable Archive](https://www.dfs.ny.gov/public-appeal/search)
describes a database of closed New York external appeals with case summaries and
outcomes. The archive page advertises filters for diagnosis, treatment, health
plan, decision, appeal type, coverage type, age range, decision year, appeal
agent, case number, summary, and references, plus an all-data-by-year Excel
export. The official [external-appeal description](https://www.dfs.ny.gov/complaints/file_external_appeal)
confirms that these reviews concern denials based on medical necessity,
experimental/investigational treatment, or out-of-network care, and that the
external agent may uphold or overturn the denial.

This is the strongest substitute found for regulator-determined denial
rationales and outcomes. It is not automatically equivalent to a source of
original denial letters: the archive exposes summaries, and the presence of a
prior-authorization denial must be established from its `Appeal Type`, treatment,
and summary fields rather than assumed. It also does not provide the claimant's
clinical chart. If accepted, it will be used for external evaluation of denial
language and outcome only; Synthea remains the separate synthetic chart corpus.

The official archive page returned HTTP 403 with a Cloudflare challenge to the
current command-line environment on 2026-08-26. The user then manually exported
`peasadata.xlsx` from the archive in a browser on 2026-08-26. The workbook is an
all-years export, not the intended 2024-only slice; its decision-year values run
from 2019 through 2026. The rendered browser table showed 55,571 records at the
time of the export, while the workbook contains 61,606 data rows. That
rendered-count/export-count discrepancy is recorded as a gap rather than
silently reconciled.

The [DFS privacy policy](https://www.dfs.ny.gov/privacy) states that browsing or
downloading publicly available information is generally available, but that is
not a dataset redistribution licence. The raw workbook remains in the user's
Downloads directory and is not committed or redistributed. Its metadata-only
inspection is recorded in `evidence/ny-dfs-export-acquisition.json`; the
inspection script is `scripts/inspect_ny_export.py`. The project owner sent the
schema/reuse request recorded in `docs/ny-dfs-review-request.md` on 2026-08-27;
no written response is recorded yet.

## Manual NY DFS export inspection

The local artifact is an OOXML XLSX workbook named `peasadata.xlsx`, 67,128,160
bytes, with SHA-256
`999c8bb5338844cd56d90db11a3c8691af887592f2956a62418bbddfa9c4876a`. It has one
sheet (`Sheet0`), dimension `A1:S61607`, 61,606 data rows, 19 columns, and
243,367 unique shared strings. The exact inspected headers are:

```text
Case Number | Diagnosis | Treatment | Health Plan | Coverage Type |
Appeal Decision | Denial Reason | Gender | Age Range | Decision Year | Agent |
Summary 1 | Summary 2 | Summary 3 | Summary 4 | References 1 | References 2 |
References 3 | References 4
```

The export has no explicit `Appeal Type` column; `Denial Reason` is present and
contains Medical necessity (55,316), Experimental/Investigational (2,245),
Formulary Exception (3,961), Step Therapy (78), and Out-of-Network Service (6).
The outcome field contains 28,280 `Overturned`, 1,166 `Overturned in Part`, and
32,160 `Upheld` rows. Summary 1 and References 1 are populated for all 61,606
rows. There are 60,356 distinct case-number values, 1,357 diagnoses, 104
treatments, 98 health plans, and 6 appeal agents. The export therefore has
case-level outcome-shaped data, but prior-authorization eligibility still needs
to be established from the denial-reason, treatment, and narrative fields rather
than assumed.

The privacy scan covered distinct values from Summary 1 through Summary 4 and
emitted no narrative text or case number. It found zero email-shaped values and
zero SSN-shaped values, but it also found 140 physical-address-shaped values, 8
date-of-birth labels, and 9 member-ID labels. These are unreviewed identifier
candidates, so the artifact is **blocked from corpus acceptance**. The additional
word-level counts were 2,402 `address`, 89 `street`, 6 `avenue`, 26 `road`, and
no confirmed date/member value was accepted. The scan is conservative: a shape
candidate is enough to stop acceptance until a human privacy review or a
permitted redaction workflow resolves it.

The current count is therefore **one manually acquired NY DFS export artifact**,
**61,606 rows observed locally**, **zero accepted public evaluation-corpus
records**, **zero Appeal evaluations**, and **zero regulator-ground-truth
comparisons**. This is schema/provenance progress, not a Phase 9 result.

Verification commands and results:

```text
python3 scripts/inspect_ny_export.py /Users/user/Downloads/peasadata.xlsx
  data_rows=61606; columns=19; appeal_type_column_present=false
  distinct_summary_values_scanned=64934
  physical_address_shape=140; date_of_birth_label=8; member_id_label=9
shasum -a 256 /Users/user/Downloads/peasadata.xlsx
  999c8bb5338844cd56d90db11a3c8691af887592f2956a62418bbddfa9c4876a
```

The inspector was run locally after the workbook download and is intentionally
an aggregate-only command: it does not print summaries, references, or case
numbers.

### Oregon Division of Financial Regulation — strongest live fallback

The [official Oregon IRO Case Detail Report](https://dfr.oregon.gov/insure/health/understand/coverage/Pages/iro-decision-report.aspx)
describes a quarterly, rolling-four-year report of completed external-review
cases. Oregon explicitly says that the external review is a document review
that produces a final case synopsis, and lists the report fields, including
review type, decision date, case outcome, case category, and the full
procedure/service/treatment name. The same page says that redacted synopsis
reports can be requested by case number from
`Exreview.Ins@dcbs.oregon.gov`.

On 2026-08-27 an unchanged workbook was downloaded from Oregon's official
Excel link and kept in `/Users/user/Downloads/oregon-iro-case-detail-report.xlsx`.
The local metadata-only inspection is
`evidence/oregon-iro-acquisition.json`, produced by
`scripts/inspect_oregon_iro.py`. It records 2,230 data rows, nine observed
fields, 2,230 distinct external-review case numbers, an explicit `Case Outcome`
field, and a free-text treatment field. The technical pattern scan found no
email, phone, SSN, date-of-birth-label, member-ID-label, or physical-address
matches in the inspected values; that is not a legal privacy determination and
does not replace human review.

The workbook is a real regulator case-detail source, not an aggregate
calibration report. The project owner has authorized local-only use of the
1,640 rows whose outcomes are completed external-review determinations
(`Upheld Denial`, `Overturned Denial`, or `Partial Overturn`). The acceptance
decision is recorded in `evidence/oregon-acceptance.json`. This is not a claim
of prior-authorization eligibility, written regulator permission, or
redistribution rights. The adapter preflight has now exercised the state
machine for all 1,640 rows, but every row abstained before denial parsing
because the report has no denial narrative, policy reference, or clinical
evidence. No case has completed Appeal. The raw workbook is unchanged,
local-only, and not committed; case numbers and free
text are generated into a separate local evaluation file outside the
repository. The written request in `docs/oregon-iro-review-request.md` is now
an optional follow-up for confirmation and redacted synopses.

The local input is reproducible with:

```text
make prepare-oregon-local-evaluation \
  OREGON_IRO_INPUT=../Downloads/oregon-iro-case-detail-report.xlsx \
  OREGON_IRO_LOCAL_OUTPUT=../Downloads/oregon-iro-local-evaluation.json
```

The command verifies the recorded workbook hash and writes the selected free
text only outside the repository. It prepares input; it does not run the full
Appeal workflow or produce regulator-comparison metrics. The adapter preflight
can be reproduced with:

```text
make run-oregon-local-evaluation \
  OREGON_IRO_LOCAL_OUTPUT=../Downloads/oregon-iro-local-evaluation.json
```

The aggregate result is `evidence/oregon-evaluation.json`.

### California Department of Insurance — California-specific candidate

The [California Department of Insurance health page](https://www.insurance.ca.gov/01-consumers/110-health/)
links to an Independent Medical Review Statistics Searchable Database. The
California statute describes a searchable, privacy-protected database of
director decisions adopting independent review determinations, including
diagnosis, disputed service, review type, reviewer criteria, final result, year,
and a detailed case summary. This is a distinct regulator and host from DMHC.

The current CDI link resolves to the Oracle APEX application `f?p=192`. A
direct request from this environment returned a redirect to `LOGIN_DESKTOP`,
while the older `/IMR/faces/search` URL returned HTTP 404. No case record or
export was obtained, and statutory publication does not by itself establish a
licence to redistribute the records. CDI remains the first manual/browser path
to try because it preserves California relevance, but it is not yet a usable
corpus.

### Michigan Department of Insurance and Financial Services — rich secondary

The [official PRIRA Orders page](https://www.michigan.gov/difs/legal/hearings-decisions/prira)
states that its PDFs are formal external-review determinations and include the
health plan, disputed treatment, certificate benefits, independent-review
findings, and the director's decision to reverse or uphold the insurer. This is
case-level narrative material and is technically promising for a small,
manually curated secondary set. The [Michigan terms of use](https://www.michigan.gov/som/footer/policies)
prohibit automated access and prohibit copying, distributing, modifying, or
commercially using site data unless an exception in law or separate written
permission applies. Therefore no automated request was made for a PRIRA PDF.
An authorized human may download a single order through the official page for
local inspection, but the raw file and any derived public dataset must remain
out of the repository unless the reuse position is cleared in writing. It is
not an unrestricted evaluation corpus. One order was obtained through that
manual path and inspected as a local-only candidate; the inspection record is
below.

## Manual Michigan artifact inspection

On 2026-08-26 the user manually downloaded the official
[BCC 237502 order](https://www.michigan.gov/difs/-/media/Project/Websites/difs/PRIRA/2025/August/BCC_237502.pdf)
from the Michigan DIFS PRIRA source. The raw PDF remains in the user's local
Downloads directory and is not committed or redistributed. The metadata-only
record is `evidence/manual-review-acquisition.json`.

The local artifact is 137,369 bytes, PDF 1.7, five pages, and has SHA-256
`e59b85c75b793eba66990eef6ca2962bf1ac2136d8945427bba5f72207be5f51`. A
temporary `pypdf` extraction found the insurer's quoted denial rationale, the
independent review analysis, and the Director's final disposition. The order
identifies the disputed laboratory-testing codes as 81270 and 81219 and states
that the Director reversed the insurer's adverse determination and ordered
coverage.

The extraction review found no petitioner name, age, contact details, member-ID
label, date-of-birth label, address label, phone pattern, email pattern, or
SSN-like pattern in page text. The document uses blank or omitted fields rather
than an explicit `[redacted]` marker, so this is recorded as an omitted-field
review and not a guarantee of complete de-identification. The PDF was
unencrypted and contained no embedded attachments or annotations.

The Michigan [site policies](https://www.michigan.gov/som/footer/policies)
restrict automated access and restrict copying, modification, distribution,
publication, commercial use, and resale without a lawful exception or prior
written permission. Accordingly, the count is **one manually acquired local
regulator-order candidate**, **zero public evaluation-corpus records**, **zero
Appeal evaluations**, and **zero regulator-ground-truth comparisons**. The
document is not the original insurer denial letter; it is a regulator order
that quotes the denial rationale. No Phase 9 hard-stop result exists yet.

### Washington Office of the Insurance Commissioner — promising, access pending

The [official Washington online-services page](https://www.insurance.wa.gov/online-services)
and [appeals guidance](https://www.insurance.wa.gov/insurance-resources/health-insurance/appealing-health-insurance-denial/how-appeal-health-insurance-denial)
describe a public IRO decision search by company, diagnosis, treatment,
decision, and reason for appeal. The [official reporting documentation](https://www.insurance.wa.gov/sites/default/files/documents/IRO-carrier-reporting-instructions.pdf)
also describes case-detail access and redacted public decisions. The current
search endpoint and an export path were not verified from this environment, so
this is a candidate only.

### California Division of Workers' Compensation — rejected for this benchmark

The [DWC IMR search](https://www.dir.ca.gov/dwc/imr/imrdecisionsearch.asp)
publishes workers' compensation IMR index fields and links case numbers to
Final Determination Letters. The [DWC IMR decisions page](https://dir.ca.gov/DWC/IMR/IMR-Decisions/IMR_Decisions.asp)
states that those letters contain the rationale for each requested treatment.
This is a real regulator source, but it is workers' compensation rather than a
commercial-health prior-authorization corpus. The public index does not expose
the underlying denial packet, policy criteria, or complete clinical submission,
and no reproducible bulk case-level export or standalone FDL was verified here.
It is therefore excluded from the primary benchmark. A DWC letter may still be
useful for parser testing if a separately authorized, local-only document is
obtained; it must not be presented as equivalent to the DMHC health-plan source.

### Texas and Pennsylvania — useful but not primary equivalents

The [Texas Department of Insurance IRO page](https://www.tdi.texas.gov/hmo/mcqa/iro_decisions.html)
publishes redacted case decisions, but the page explicitly identifies the
collection as workers' compensation IRO decisions. It is useful for parser
robustness, not as a commercial-health prior-authorization benchmark.

The [Pennsylvania Insurance Department's external-review process](https://www.pa.gov/services/insurance/request-a-review-if-your-health-insurance-denied-a-treatment-medication-or-service)
is directly relevant to denied health services, and its [2024 report](https://www.pa.gov/content/dam/copapwp-pagov/en/insurance/documents/departments-and-offices/hca3/doc-library/2024-annual-report-summary.pdf)
publishes counts and outcomes. It does not expose a public case-summary archive
in the material reviewed, so it is aggregate calibration evidence only.

### Source decision

No source is currently verified as complete end-to-end. For this project,
"complete" means a public, provenance-preserving case record with a denial
basis, requested service, usable clinical rationale, regulator outcome, and a
defensible prior-authorization scope decision. The ranked retrieval order is
now: (1) obtain and inspect the official DMHC case-level resource or an
official DMHC searchable record; (2) if that remains inaccessible, try the
California CDI and Washington OIC case-level paths; (3) continue NY DFS only
through its explicit mapping, privacy, reuse, and prior-authorization gates;
and (4) treat Oregon as outcome-only until a denial packet or redacted synopsis
supplies the missing inputs. Pennsylvania and CMS remain aggregate calibration
sources. DWC is excluded for scope and completeness reasons.

The project currently has **zero real denial cases evaluated and zero
regulator-ground-truth comparisons**. It has three metadata-only source
artifacts plus a local-only Oregon evaluation input. The Oregon adapter
preflight is recorded, but it abstained on every row and did not produce an
Appeal score. No README, evaluation file, demo case, or metric may claim an
Appeal evaluation until a full adapter run and comparison are recorded.

The two-corpus boundary remains explicit: regulator records can test denial
language, criterion-location reasoning, and externally recorded outcomes;
Synthea records can test chart retrieval, evidence sufficiency, and the
Evidence Floor. A real regulator case must never be joined to a synthetic
patient or presented as if its chart were available.

## CMS benchmark definition

The authoritative benchmark definition is:

- [CMS Prior Authorization API FAQ](https://www.cms.gov/initiatives/burden-reduction/overview/interoperability/frequently-asked-questions/prior-authorization-api)
- [CMS Prior Authorization Metrics Reporting — Overview and Template](https://www.cms.gov/prior-authorization-metrics-reporting-overview-template)
- [CMS-0057-F fact sheet](https://www.cms.gov/newsroom/fact-sheets/cms-interoperability-prior-authorization-final-rule-cms-0057-f)

The CMS FAQ and template establish that 2025 metrics were first due publicly
by March 31, 2026, and that the figures are aggregated across medical items and
services but reported at the applicable contract, state, plan, or issuer level.
They define approval, denial, approval-after-appeal, and timing metrics. They
are not a central case-level outcome dataset. Actual payer/program reports must
be collected individually with URL, timestamp, ETag, and content hash before
they are used to calibrate the reference payer.

## Gaps

- The DMHC resource is officially catalogued as covering all IMR decisions
  since 2001 and is declared CC BY, but its case-level schema has not been
  inspected because the downloadable payload and datastore remain behind the
  same Cloudflare-protected host. The lab catalog is a metadata route, not a
  second data copy.
- One official Michigan regulator order has been inspected locally; no raw real
  document or derived public case dataset has been accepted into the
  repository.
- The Oregon IRO Case Detail Report is a real regulator case-level source with
  2,230 observed rows and explicit outcome fields. The project owner accepted
  1,640 completed-review rows for local-only outcome evaluation. Its raw
  workbook, case numbers, and free text remain outside the repository; no
  prior-authorization claim or redistribution permission is asserted. The
  adapter preflight ran against all 1,640 rows and abstained before denial
  parsing; no full Appeal case was evaluated.
- The NY DFS export has 61,606 locally observed rows, but the privacy scan found
  unreviewed physical-address-shaped, date-of-birth-label, and member-ID-label
  candidates. Its reuse licence is also not established by the DFS privacy
  policy. It remains local-only and is not an accepted evaluation corpus.
- The NY browser table and downloaded workbook disagree on the visible record
  count (55,571 versus 61,606); the reason has not been established.
- No CMS payer report has yet been collected as calibration evidence.
- No real denial has completed Appeal, so the Phase 9 hard-stop report does not
  exist yet. The adapter preflight is an explicit input-gap report, not a
  performance result.

## Blockers

- Phase 1D's Oregon adapter preflight is complete, but the accepted subset
  contains no denial narrative, policy reference, or clinical evidence, so all
  1,640 rows abstained before a full Appeal evaluation. It cannot claim
  prior-authorization eligibility or public corpus redistribution. One Michigan
  order remains local-only and unevaluated. The NY DFS export remains blocked
  by its mapping, privacy, and reuse decisions. DMHC is the primary retrieval
  target; CDI and Washington are the next case-level alternatives. DWC is not
  an equivalent health-plan benchmark.
- Phase 2 payer calibration cannot claim a target distribution until actual
  public 2025 reports are collected and hashed.
- The overall build remains stopped at the Phase 0 billing/model-discovery
  blocker recorded in `docs/audits/phase-0.md`.

## Exit status

Pre-credit source discovery has identified three manually acquired regulator
artifacts: one Michigan order, one NY DFS export, and one Oregon IRO workbook.
The official DMHC dataset is the primary next retrieval target, but no DMHC
payload has been accepted. Oregon is accepted for local-only external-review
outcome handling, and its adapter preflight is recorded as 1,640 explicit
abstentions. No full Appeal evaluation or regulator-ground-truth comparison
has been completed. The project must not claim performance until those results
are recorded.
