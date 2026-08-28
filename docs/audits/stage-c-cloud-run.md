# Stage C — Cloud Run backend deployment

**Recorded:** 2026-08-28

The Appeal HTTP backend is deployed to Google Cloud Run in project
`onyx-yeti-506606-i9` (display name `Appeal`), region `europe-west2`.

| Field | Verified value |
|---|---|
| Service | `appeal-backend` |
| Revision | `appeal-backend-00002-d24` |
| Traffic | 100% to the listed revision |
| Service URL | <https://appeal-backend-hhcjpefk2q-nw.a.run.app> |
| Runtime identity | `appeal-backend@onyx-yeti-506606-i9.iam.gserviceaccount.com` |
| Source commit | `924b69f` |

The public `/api/healthz` endpoint returned `status: ok`. A synthetic case was
then exercised through the deployed service: creation, clinician approval,
one submission mutation, and payer adjudication to `CLOSED_WON`. The
aggregate-only record is `evidence/cloud-run-deployment.json`.

This proves a reachable Google Cloud backend for the synthetic demo path and
provides the Cloud Run evidence required by the hackathon setup. It does not
claim a production deployment: the service is intentionally unauthenticated,
uses process-local in-memory state, accepts no real case data, and exposes the
deterministic API facade. Agent Runtime, Agent Registry, Agent Identity,
Firestore, Pub/Sub, managed Memory Bank, Agent Gateway, Firebase Auth, and a
live default Model Armor/Gemma workflow boundary remain separate
implementation work. Separate synthetic provider measurements are recorded in
`evidence/model-armor-measurement.json` and
`evidence/gemma-tripwire-measurement.json`.

No raw denial, clinical, member, payer, or other real-case data was uploaded.
