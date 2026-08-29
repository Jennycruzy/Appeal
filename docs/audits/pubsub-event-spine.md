# Pub/Sub event spine audit

Recorded: 2026-08-29

Appeal now publishes reference-only workflow events through the managed
`appeal-events` topic in project `onyx-yeti-506606-i9`. The Cloud Run runtime
uses the `appeal-backend` service account, which has publisher access scoped to
that topic. Firestore registers each event at
`appeal_tenants/{tenant_id}/cases/{case_id}/events/{event_id}` before publish
and marks it published after the Pub/Sub acknowledgement. Replays of a
published event are no-ops; a pending event may be retried, and the stable
event ID is carried as the consumer idempotency key.

The push subscription is
`appeal-events-to-backend`, with a 60-second acknowledgement deadline and
endpoint
`https://appeal-backend-835653516606.europe-west2.run.app/api/events/pubsub`.
It mints OIDC tokens as the dedicated
`appeal-pubsub-push@onyx-yeti-506606-i9.iam.gserviceaccount.com` identity. That
identity has Cloud Run Invoker on the Appeal service; the Pub/Sub service agent
is allowed to mint only that identity's token. The endpoint validates the
audience and service-account email before decoding the message.

The message body is a validated `DomainEvent`: tenant and case identifiers,
topic, idempotency key, timestamp, and scalar metadata only. The event schema
rejects raw content fields such as denial bodies, chart data, prompts, prose,
and text. The push receiver records an already-published event without
publishing it back to the same topic, preventing a delivery loop. No push
message can grant approval or perform an external mutation.

Hosted verification on revision `appeal-backend-00016-p7s` returned:

- `/api/healthz` reported `event_spine: pubsub_firestore`;
- an anonymous request to `/api/events/pubsub` was rejected with HTTP 401;
- one fresh synthetic case produced thirteen workflow events; and
- Cloud Run access logs recorded thirteen authenticated push deliveries with
  HTTP 200 responses.

Subscriber-driven agent execution is not claimed yet. The current subscriber
acknowledges and registers validated events; managed Agent Runtime, Registry,
Identity, Gateway, Policies, Memory Bank, Observability, and the separate
payer service remain the next product integrations. No real case data was
uploaded.
