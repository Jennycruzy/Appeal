# Pre-credit policy-source discovery

Audit date: 2026-08-25

## CMS Medicare Coverage Database candidate

The rejected Aetna and Cigna endpoints are not the only possible policy source.
The [CMS Medicare Coverage Database downloads page](https://www.cms.gov/medicare-coverage-database/downloads/downloads.aspx)
publishes current LCD, Article, and NCD datasets and links to the Coverage API.
The page says the current NCD archive is a separate dataset and that the
downloads are updated weekly. It also presents separate AMA CPT, ADA CDT, and
AHA UB-04 licence agreements.

The live preflight result for `cms_mcd_ncd` is `warning`:

- `https://www.cms.gov/robots.txt` returned HTTP 200 and permits the MCD path.
- The CMS MCD page returned HTTP 200.
- `automated_fetch_authorized` remains `false`.
- `policy_fetch_performed` remains `false`.

The candidate is restricted to policy text whose terms permit the intended use;
restricted CPT/CDT/UB-04 data will not be copied into the repository or emitted
in generated output. The [MCD search guidance](https://www.cms.gov/medicare-coverage-database/search.aspx)
also confirms that NCDs and LCDs are coverage documents, while procedure-code
content is often in Articles. That distinction matters for the code-scoped
criterion locator.

## Gaps

- The selected NCD or LCD document has not been chosen.
- The licence terms for the selected document have not been accepted or
  recorded for the project's intended noncommercial use.
- The download response has not been validated for an ETag-backed cache.
- No policy document has been fetched.

## Blockers

Automated CMS policy ingestion is blocked until a human terms review identifies
an allowed document and use. The source is a candidate, not an authorization.

## Exit status

Discovery is complete; policy ingestion remains disabled.
