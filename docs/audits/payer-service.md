# Separate payer service audit

Recorded 2026-08-31 in `onyx-yeti-506606-i9` / `europe-west2`.

`appeal-payer-00001-j9g` is a separate private Cloud Run service running under
`appeal-payer@onyx-yeti-506606-i9.iam.gserviceaccount.com`. The backend service
account has the only `roles/run.invoker` binding. An unauthenticated request was
rejected with HTTP 403. A temporary operator token-creator grant on the backend
identity was used for one positive probe and revoked immediately afterward;
the final service-account policy has no such grant.

The service is stateless and synthetic-only. It owns a private copy of the
demo payer criterion and accepts only tenant/case identifiers, a scoped payer
idempotency key, and bounded evidence observations containing reference fields.
It does not import or instantiate `CaseStore`, read a chart, expose the
Submission Gate, or perform an external mutation. Unsupported top-level fields
such as `chart` are rejected.

One authenticated request using the backend service identity returned a
favorable determination with two evidence references and
`external_mutation_count: 0`. The service response contains aggregate decision
metadata only. The contract implementation is in
[`src/appeal_payer_service/`](../../src/appeal_payer_service/), the runner is
[`scripts/run_payer_service.py`](../../scripts/run_payer_service.py), and the
aggregate probe is in
[`evidence/payer-service.json`](../../evidence/payer-service.json).

This proves service separation and authorization, not a real payer API,
real claims data, or a real submission/withdrawal.
