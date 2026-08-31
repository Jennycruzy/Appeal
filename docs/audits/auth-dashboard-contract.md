# Authentication and mobile approval contract

Recorded 2026-08-31.

The case-board HTTP facade now has an opt-in fail-closed Firebase path. When
`APPEAL_FIREBASE_AUTH_REQUIRED=true`, every tenant-scoped case read and action
requires a verified Firebase ID token. The verifier uses the Firebase project
audience and requires a non-empty `tenant_id` custom claim; a missing token is
HTTP 401 and a token for another tenant is HTTP 403. The synthetic local runner
leaves this switch off so existing fixture commands remain reproducible.

Clinician approval links are short-lived HMAC capabilities containing only a
tenant ID, case ID, purpose, expiry, and nonce. A forged or expired link is
rejected, and the approval-link issuance route always requires the authenticated
tenant principal. The mobile POST accepts only the explicit `approve` action,
which resumes the existing Submission Gate path and preserves its one-mutation
invariant. Link tokens are not written to receipts or evidence artifacts.

The contract is exercised by `tests/test_auth_and_mobile.py` for authentication
failure, tenant isolation, link tamper/expiry rejection, and a successful
synthetic mobile approval. This is implementation and local contract evidence,
not hosted Firebase proof. The current project has no Firebase project yet:
the APIs are enabled, but `addFirebase` returned `PERMISSION_DENIED` until the
owner account accepts Firebase Terms in the Firebase Console. The exact
read-only boundary is recorded in
[`evidence/firebase-auth-boundary.json`](../../evidence/firebase-auth-boundary.json).

Once the owner accepts the Terms and links Firebase, deploy with:

```text
APPEAL_FIREBASE_AUTH_REQUIRED=true
APPEAL_FIREBASE_PROJECT_ID=onyx-yeti-506606-i9
APPEAL_MOBILE_LINK_SECRET='<secret from Secret Manager; never commit it>'
```

The remaining hosted work is to create synthetic clinician accounts, configure
the `tenant_id` custom claim, publish a Firebase Hosting dashboard, and capture
an authenticated browser/mobile trace. No real case data is permitted in that
proof.
