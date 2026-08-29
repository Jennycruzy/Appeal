# Managed security boundary on Cloud Run

**Recorded:** 2026-08-29

The synthetic-only Appeal backend in project `onyx-yeti-506606-i9` was
redeployed to Cloud Run revision `appeal-backend-00011-b8j` in
`europe-west2`. The service runs as
`appeal-backend@onyx-yeti-506606-i9.iam.gserviceaccount.com` with
`roles/datastore.user`, `roles/aiplatform.user`, and
`roles/modelarmor.user`.

The hosted `/api/healthz` response reported:

```text
deployment=cloud_run
storage=firestore
security=managed_model_armor_gemma
status=ok
```

The managed boundary calls Model Armor first and Gemma second. One fresh
synthetic clean case passed all three configured surfaces— inbound document,
egress draft, and memory-bank content—then completed the clinician approval,
single submission mutation, and local payer adjudication path to
`CLOSED_WON`. The security provider reported `clear` for all three surfaces.

One fresh synthetic injection case was then submitted through the same hosted
endpoint. Model Armor matched the inbound value, the case entered
`QUARANTINED`, no denial-parser transition occurred, and the external mutation
count remained `0`. Because the first provider blocked the value, Gemma was not
invoked for that hostile input; this is the intended series behavior.

The aggregate record is
[`evidence/cloud-run-deployment.json`](../../evidence/cloud-run-deployment.json).
The endpoint remains unauthenticated and synthetic-only. No real case data,
patient identifier, denial narrative, or clinical chart was uploaded. This
proves the hosted Model Armor -> Gemma workflow boundary, not managed Agent
Runtime, Pub/Sub, Memory Bank, Firebase Auth, or a complete Appeal evaluation.
