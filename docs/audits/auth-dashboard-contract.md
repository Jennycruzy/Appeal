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
synthetic mobile approval. The hosted boundary is now also verified: Firebase
Auth is initialized with Email/Password enabled, the synthetic clinician
account carries `tenant_id=tenant-demo-hosted`, the Firebase Hosting dashboard
returns HTTP 200, and the tenant-scoped Cloud Run board returns HTTP 200 for
six synthetic cases. The aggregate boundary record is
[`evidence/firebase-auth-boundary.json`](../../evidence/firebase-auth-boundary.json).

The authenticated Cloud Run deployment uses:

```text
APPEAL_FIREBASE_AUTH_REQUIRED=true
APPEAL_FIREBASE_PROJECT_ID=onyx-yeti-506606-i9
APPEAL_MOBILE_LINK_SECRET='<secret from Secret Manager; never commit it>'
```

The remaining hosted work is to capture the authenticated browser/mobile trace
and finish the final video/submission metadata. No real case data is permitted
in that proof.
