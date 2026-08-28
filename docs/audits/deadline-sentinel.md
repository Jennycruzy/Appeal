# Deadline Sentinel audit

Recorded: 2026-08-28

The Appeal Deadline Sentinel is exposed as a dedicated `POST
/api/sentinel/tick` route. It reads only tenant-scoped persisted case state,
checks the case-bound statutory clock, and uses the existing deterministic
state machine to close an expired executable case as
`CLOSED_ABANDONED_DEADLINE`. It does not read or reconstruct denial content,
chart content, model responses, or draft prose.

Cloud Scheduler job `appeal-deadline-sentinel` is enabled in `europe-west2`
with schedule `0 * * * *` in UTC. It sends an OIDC token for
`appeal-scheduler@onyx-yeti-506606-i9.iam.gserviceaccount.com` to the regional
Cloud Run URL. The service account has Cloud Run Invoker on the Appeal service;
the route additionally verifies the token audience and service-account email
because the synthetic demo service remains public for its other endpoints.

The verification run seeded two synthetic expired cases using
`scripts/seed_sentinel_case.py`. An anonymous tick returned HTTP 401. A
manual execution of the real Scheduler job returned successfully, Cloud Run
logged HTTP 200, and both seeded cases reached
`CLOSED_ABANDONED_DEADLINE`. Each retained its original single submission
mutation count; the Sentinel performed no new external mutation.

The aggregate deployment and Scheduler record is
[`evidence/cloud-run-deployment.json`](../../evidence/cloud-run-deployment.json).
The seed metadata is in
[`evidence/sentinel-seed.json`](../../evidence/sentinel-seed.json) and
[`evidence/sentinel-seed-002.json`](../../evidence/sentinel-seed-002.json).

The receipt ledger for this container remains local, so the next audit item is
durable receipt/event delivery through the managed event spine. This audit
does not claim Agent Runtime, Pub/Sub, Memory Bank, Firebase Auth, or a real
case workflow deployment.
