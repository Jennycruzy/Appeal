from __future__ import annotations

import unittest
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from appeal_service import (
    ApprovalLinkError,
    ApprovalLinkSigner,
    FirebasePrincipal,
    LocalAppealService,
    LocalHttpApi,
    PrincipalVerifier,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


class FixedPrincipalVerifier(PrincipalVerifier):
    def __init__(self, tenant_id: str) -> None:
        self.principal = FirebasePrincipal("uid-demo-clinician", tenant_id, "clinician@example.test")

    def verify(self, headers: Mapping[str, str]) -> FirebasePrincipal:
        if headers.get("X-Demo-Auth") != "ok":
            from appeal_service import AuthenticationError

            raise AuthenticationError("missing test credential")
        return self.principal


def api_for(tenant_id: str = "tenant-demo-auth") -> LocalHttpApi:
    return LocalHttpApi(
        LocalAppealService.for_repository(str(ROOT)),
        firebase_auth_required=True,
        firebase_verifier=FixedPrincipalVerifier(tenant_id),
        mobile_link_secret="s" * 32,
        mobile_link_ttl_seconds=300,
    )


class AuthAndMobileTests(unittest.TestCase):
    def test_case_routes_fail_closed_and_enforce_tenant(self) -> None:
        api = api_for()
        status, body = api.handle("GET", "/api/cases/tenant-demo-auth", at=NOW)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "authenticated_user_required")

        status, body = api.handle(
            "GET",
            "/api/cases/tenant-other",
            headers={"X-Demo-Auth": "ok"},
            at=NOW,
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "tenant_access_denied")

    def test_signed_mobile_link_requires_auth_and_approves_once(self) -> None:
        api = api_for()
        headers = {"X-Demo-Auth": "ok"}
        status, created = api.handle(
            "POST",
            "/api/demo/cases",
            {"tenant_id": "tenant-demo-auth", "case_id": "case-demo-auth"},
            headers=headers,
            at=NOW,
        )
        self.assertEqual(status, 201)
        self.assertEqual(created["case_state"], "AWAITING_CLINICIAN")

        status, link_body = api.handle(
            "POST",
            "/api/cases/tenant-demo-auth/case-demo-auth/approval-link",
            headers=headers,
            at=NOW,
        )
        self.assertEqual(status, 201)
        token = link_body["approval_link"]
        self.assertIsInstance(token, str)

        status, preview = api.handle("GET", f"/api/mobile/approval/{token}", at=NOW)
        self.assertEqual(status, 401)
        self.assertEqual(preview["error"], "authenticated_user_required")

        status, preview = api.handle(
            "GET",
            f"/api/mobile/approval/{token}",
            headers=headers,
            at=NOW,
        )
        self.assertEqual(status, 200)
        self.assertEqual(preview["case_id"], "case-demo-auth")
        self.assertEqual(preview["case_state"], "AWAITING_CLINICIAN")

        status, approved = api.handle(
            "POST",
            f"/api/mobile/approval/{token}",
            {"decision": "approve"},
            headers=headers,
            at=NOW + timedelta(seconds=1),
        )
        self.assertEqual(status, 200)
        self.assertEqual(approved["case_state"], "AWAITING_DETERMINATION")
        self.assertEqual(approved["external_mutation_count"], 1)

    def test_signed_link_rejects_tampering_and_expiry(self) -> None:
        signer = ApprovalLinkSigner("s" * 32, ttl_seconds=10)
        token = signer.issue("tenant-demo", "case-demo", now=NOW)
        with self.assertRaises(ApprovalLinkError):
            signer.verify(token[:-1] + ("A" if token[-1] != "A" else "B"), now=NOW)
        with self.assertRaises(ApprovalLinkError):
            signer.verify(token, now=NOW + timedelta(seconds=10))


if __name__ == "__main__":
    unittest.main()
