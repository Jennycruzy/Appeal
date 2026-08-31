# Hosted asynchronous workflow audit

Recorded 2026-08-31 against Cloud Run revision `appeal-backend-00026-42q` in
`onyx-yeti-506606-i9` / `europe-west2`.

The hosted synthetic path was exercised as:

```text
Cloud Run case creation -> clinician approval -> AWAITING_DETERMINATION
  -> Pub/Sub topic -> authenticated OIDC push -> Cloud Run
  -> Firestore session resume -> payer determination -> CLOSED_WON
```

The case was `case-hosted-payer-clean-20260831-revision26-155327` in the
synthetic tenant `tenant-demo-hosted-payer-clean-20260831-revision26-155327`.
The payer event contained only
`decision`, `criterion_status`, and `evidence_ref_count` metadata. It contained
no denial text, chart resource, patient identifier, or model response.

The first delivery returned HTTP 200 and moved the persisted case from
`AWAITING_DETERMINATION` to `CLOSED_WON`. The external mutation count stayed at
one. Republishing the same event ID returned HTTP 200 and left the state and
mutation count unchanged. Firestore showed one processed event ID, matching
case/session fingerprints, and the reference-only payer event in the case event
collection.

The deployed follow-up also exercised the failure boundary that had been
observed during the prior revision-23 attempt. Case state and its resumable
session are now written in one Firestore transaction, and a managed security
provider outage can persist a fail-closed quarantine without turning the API
response into a misleading write failure. The push receiver accepts the
standard wrapped Pub/Sub body and the authenticated no-wrapper form; both still
pass through the same typed event and reference-only payload validation.

The Pub/Sub subscription uses the dedicated
`appeal-pubsub-push@onyx-yeti-506606-i9.iam.gserviceaccount.com` OIDC identity and
the regional Cloud Run audience. The aggregate request and state evidence is
in [`evidence/cloud-run-async-workflow.json`](../../evidence/cloud-run-async-workflow.json).

During earlier hosted advisory-checkpoint traffic, Vertex shared-capacity
failures produced retryable managed Runtime records. The workflow event was
still acknowledged after durable handling; the advisory result is explicitly
reported as failed/retryable and cannot mutate a case. This keeps provider
capacity failures from redelivering or duplicating a durable workflow action.

This is a synthetic workflow proof. It does not establish a real payer
integration, a Firebase-authenticated console, a mobile notification loop, or a
full real-case clinical evaluation.
