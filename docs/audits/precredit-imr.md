# Pre-credit real-corpus discovery

Audit date: 2026-08-26

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
January 1, 2001. Those statements establish provenance and a licence lead; they
do not yet prove that the downloadable `Trend` resource contains the case-level
denial rationale and determination fields required by Phase 1D.

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
2026-08-26:

- A plain GET of the official CSV returned HTTP 403.
- A GET with a current Safari User-Agent, Referer, Accept headers, and a 1 KB
  Range request also returned HTTP 403.
- The California Open Data datastore endpoint returned HTTP 403.
- The official Data.gov catalogue was inspected. Its harvested metadata exposes
  the same CSV, ZIP, and dictionary URLs on `data.chhs.ca.gov`; it does not
  provide a separate data mirror.
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

- The DMHC resource name indicates a trend dataset, but its case-level schema
  has not been inspected because every tested official access route is behind
  the same Cloudflare restriction.
- No real redacted denial letter has been accepted into the repository.
- No CMS payer report has yet been collected as calibration evidence.
- No real denial has been run through Appeal, so the Phase 9 hard-stop report
  does not exist yet.

## Blockers

- Phase 1D cannot claim a real case-level evaluation set until the official
  DMHC data or its official searchable records can be retrieved and inspected.
  This is an unresolved retrieval blocker, not an unavailable-data finding.
- Phase 2 payer calibration cannot claim a target distribution until actual
  public 2025 reports are collected and hashed.
- The overall build remains stopped at the Phase 0 billing/model-discovery
  blocker recorded in `docs/audits/phase-0.md`.

## Exit status

Pre-credit source discovery is complete. Official retrieval remains blocked by
Cloudflare from this environment; corpus ingestion is not complete, and the
project must not advance the main phase protocol on this evidence alone.
