# Cloud persistence audit

Recorded: 2026-08-29

Appeal now has a native Firestore database in project
`onyx-yeti-506606-i9`, located in `europe-west2`. The database uses optimistic
concurrency and delete protection. The Cloud Run service account
`appeal-backend@onyx-yeti-506606-i9.iam.gserviceaccount.com` has only the
`roles/datastore.user` project binding needed by the adapter.

The Cloud Run service is revision `appeal-backend-00011-b8j`, serving 100% of
traffic. Its deployment configuration selects Firestore explicitly through
`APPEAL_STORAGE=firestore`. The adapter stores the immutable case state
machine, hashes, evidence references, and bounded metadata under the
tenant-scoped path `appeal_tenants/{tenant_id}/cases/{case_id}`. It does not
store denial prose, chart content, model responses, or draft prose.

The adapter uses Firestore's supported transactional decorator for read-then-
write operations. A current fingerprint is required for updates, and a
fingerprint mismatch or malformed/tampered payload fails closed. Local tests
cover tenant scoping, round trips, optimistic conflicts, tamper detection, and
board hydration after a process restart.

The hosted synthetic lifecycle smoke test verified:

- `/api/healthz` reported `deployment=cloud_run`, `storage=firestore`, and
  `status=ok`;
- the synthetic demo case reached `AWAITING_CLINICIAN`, then
  `AWAITING_DETERMINATION` after clinician approval, then `CLOSED_WON` after
  payer adjudication;
- the external mutation count remained exactly `1`; and
- a subsequent board request returned the persisted tenant case.

The same revision also runs the managed Model Armor -> Gemma security boundary.
Its identity bindings are recorded in the managed security audit at
[`managed-security-cloud-run.md`](managed-security-cloud-run.md). The security
smoke is synthetic-only and does not change the Firestore data boundary.

The aggregate record is [`evidence/cloud-run-deployment.json`](../../evidence/cloud-run-deployment.json).

The Deadline Sentinel now runs through the separately audited hourly
Scheduler path in [`deadline-sentinel.md`](deadline-sentinel.md).

This is not yet a complete durable Appeal service. Workflow context needed to
resume approval or adjudication is still in process memory; the receipt
ledger is still container-local; the endpoint is unauthenticated and
synthetic-only; and no real case data was uploaded. The next persistence
extension is a scoped workflow-session/receipt design, not a relaxation of the
data boundary.
