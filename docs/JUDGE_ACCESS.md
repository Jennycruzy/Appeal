# Judge access

Open the hosted Appeal board:

https://onyx-yeti-506606-i9.web.app

Use this public sandbox account:

Email: `clinician.demo@appeal.test`

Password: `AppealJudge-2026!Board`

Tenant: `tenant-demo-hosted`

This account is intentionally published for hackathon judging. It is scoped to
Appeal's no-PHI evaluation tenant. The tenant contains controlled cases and a
bounded payer adapter; it does not contain patient records or a live payer
credential.

After signing in:

1. Use **Refresh board** to read the current cases from Firestore.
2. Select **Clinician review** / `AWAITING_CLINICIAN` to inspect the denial,
   policy criterion tree, evidence-by-criterion, and draft claim provenance.
3. Select **Evidence gap** or **Security quarantine** to see safe abstention
   paths. These cases intentionally expose no approval action.
4. Select **Payer determination** / `AWAITING_DETERMINATION` to receive the
   bounded payer result and observe the durable terminal state.

The board is shared by judges. If another viewer has already advanced the
available cases, click **Load cases** once to create a fresh six-case set for
the tenant, then click **Refresh board**. All created records remain inside the
same no-PHI evaluation tenant.

The hosted board authenticates with Firebase Authentication, sends the Firebase
ID token to Cloud Run, and is authorized by the server-verified `tenant_id`
claim. The relevant deployment and boundary evidence is linked from the
[judge evidence map](JUDGING.md) and
[`evidence/firebase-auth-boundary.json`](../evidence/firebase-auth-boundary.json).

