# Durable workflow context and receipts audit

Recorded: 2026-08-29

The Appeal runtime now persists a bounded, reference-only workflow session in
Firestore at
`appeal_tenants/{tenant_id}/cases/{case_id}/workflow_sessions/current`. The
session contains the versioned policy criterion, evidence observations and
hashes, criterion evaluation, veto results, security inspection metadata,
event metadata, outcome, and payer decision. It intentionally excludes the
denial body, chart resources, model responses, claim prose, and draft prose.
The case fingerprint binds the session to the immutable Firestore case state;
stale or tampered sessions fail closed.

The cloud runtime also uses a Firestore receipt adapter at
`appeal_tenants/{tenant_id}/cases/{case_id}/receipt_ledger/current`. It keeps
the existing receipt body and hash-chain rules, compares idempotency keys
inside a Firestore transaction, and verifies the stored tip and every previous
hash. Local development continues to use the POSIX JSONL ledger.

The hosted revision-boundary smoke used synthetic case
`tenant-demo-durable/case-demo-durable-20260829`:

- revision `appeal-backend-00012-rh7` created and persisted the case awaiting
  clinician approval;
- revision `appeal-backend-00013-qzz`, after container replacement, recovered
  the session and performed the clinician co-signature and one submission
  mutation; and
- revision `appeal-backend-00014-95f`, after a second replacement, recovered
  the submitted session and completed payer adjudication to `CLOSED_WON`.

The aggregate count stayed at one external mutation. Local tests cover
Firestore session round trips, restart-safe approval and adjudication,
content-free persistence, receipt idempotency, receipt-chain verification, and
tamper detection. The full repository check completed with 83 tests passing and
strict mypy passing. No real case data was uploaded.

This closes durable workflow context and receipt persistence for the current
synthetic Cloud Run boundary. The managed Pub/Sub event boundary is recorded
separately in [`pubsub-event-spine.md`](pubsub-event-spine.md). The managed
Agent Runtime, Registry, and Identity deployment is recorded separately in
[`agent-runtime.md`](agent-runtime.md). Managed Memory Bank readback and the
current Agent Runtime trace export are verified synthetic probes. Gateway,
Policies, payer service separation, and the hosted console remain open work.
