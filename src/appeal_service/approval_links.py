"""Short-lived signed clinician approval links.

Links are bearer credentials, so the payload is deliberately minimal and the
token is never written to a receipt or aggregate evidence report.  A Firebase
principal is still required by the hosted authenticated facade; the signature
prevents a link from being edited or rebound to another tenant/case.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


class ApprovalLinkError(ValueError):
    """Raised for malformed, forged, or expired approval links."""


def _encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decoded(value: str) -> bytes:
    if not value or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for character in value):
        raise ApprovalLinkError("approval link encoding is invalid")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, UnicodeError) as error:
        raise ApprovalLinkError("approval link encoding is invalid") from error


@dataclass(frozen=True)
class ApprovalLink:
    tenant_id: str
    case_id: str
    expires_at: datetime
    nonce: str


class ApprovalLinkSigner:
    """Issue and verify HMAC-signed, expiring clinician links."""

    def __init__(self, secret: str, *, ttl_seconds: int = 900) -> None:
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("mobile approval secret must be at least 32 bytes")
        if ttl_seconds <= 0 or ttl_seconds > 24 * 60 * 60:
            raise ValueError("mobile approval TTL must be between one second and 24 hours")
        self._secret = secret.encode("utf-8")
        self.ttl_seconds = ttl_seconds

    def issue(
        self,
        tenant_id: str,
        case_id: str,
        *,
        now: datetime | None = None,
    ) -> str:
        tenant = tenant_id.strip()
        case = case_id.strip()
        if not tenant or not case:
            raise ValueError("tenant and case IDs are required")
        issued_at = (now or datetime.now(UTC)).astimezone(UTC)
        expires_at = issued_at + timedelta(seconds=self.ttl_seconds)
        payload = {
            "v": 1,
            "purpose": "clinician_approval",
            "tenant_id": tenant,
            "case_id": case,
            "exp": int(expires_at.timestamp()),
            "nonce": secrets.token_urlsafe(12),
        }
        encoded_payload = _encoded(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        signature = hmac.new(self._secret, encoded_payload.encode("ascii"), hashlib.sha256).digest()
        return f"{encoded_payload}.{_encoded(signature)}"

    def verify(self, token: str, *, now: datetime | None = None) -> ApprovalLink:
        parts = token.split(".")
        if len(parts) != 2:
            raise ApprovalLinkError("approval link format is invalid")
        encoded_payload, encoded_signature = parts
        payload_bytes = _decoded(encoded_payload)
        signature = _decoded(encoded_signature)
        expected_signature = hmac.new(self._secret, encoded_payload.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected_signature):
            raise ApprovalLinkError("approval link signature is invalid")
        try:
            payload = json.loads(payload_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ApprovalLinkError("approval link payload is invalid") from error
        if not isinstance(payload, dict):
            raise ApprovalLinkError("approval link payload is invalid")
        if payload.get("v") != 1 or payload.get("purpose") != "clinician_approval":
            raise ApprovalLinkError("approval link purpose is invalid")
        tenant_id = payload.get("tenant_id")
        case_id = payload.get("case_id")
        nonce = payload.get("nonce")
        expires = payload.get("exp")
        if (
            not isinstance(tenant_id, str)
            or not tenant_id.strip()
            or not isinstance(case_id, str)
            or not case_id.strip()
            or not isinstance(nonce, str)
            or not nonce.strip()
            or not isinstance(expires, int)
            or isinstance(expires, bool)
        ):
            raise ApprovalLinkError("approval link claims are invalid")
        try:
            expires_at = datetime.fromtimestamp(expires, tz=UTC)
        except (OverflowError, OSError, ValueError) as error:
            raise ApprovalLinkError("approval link expiry is invalid") from error
        current = (now or datetime.now(UTC)).astimezone(UTC)
        if expires_at <= current:
            raise ApprovalLinkError("approval link is expired")
        return ApprovalLink(tenant_id.strip(), case_id.strip(), expires_at, nonce.strip())
