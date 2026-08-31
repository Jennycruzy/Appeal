"""Firebase ID-token verification and tenant principal extraction.

The HTTP facade keeps authentication optional for the synthetic local runner,
but the authenticated deployment path must fail closed.  This module does
not create users or accept service-account keys; it verifies a Firebase ID
token with Google's public-key verifier and requires an explicit tenant claim.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, cast


class AuthenticationError(ValueError):
    """Raised when an ID token cannot establish a Firebase principal."""


@dataclass(frozen=True)
class FirebasePrincipal:
    """The minimum identity needed for server-side tenant authorization."""

    uid: str
    tenant_id: str
    email: str | None


class PrincipalVerifier(Protocol):
    """Verifier interface used by the HTTP facade and deterministic tests."""

    def verify(self, headers: Mapping[str, str]) -> FirebasePrincipal:
        """Verify request headers and return the authenticated principal."""


class FirebaseIdTokenVerifier:
    """Verify Firebase ID tokens for one Firebase project."""

    def __init__(self, project_id: str) -> None:
        normalized = project_id.strip()
        if not normalized:
            raise ValueError("Firebase project ID must not be empty")
        self.project_id = normalized

    def verify(self, headers: Mapping[str, str]) -> FirebasePrincipal:
        authorization = next(
            (value for key, value in headers.items() if key.lower() == "authorization"),
            "",
        )
        if not authorization.startswith("Bearer "):
            raise AuthenticationError("Bearer Firebase ID token required")
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise AuthenticationError("Bearer Firebase ID token required")
        try:
            id_token = importlib.import_module("google.oauth2.id_token")
            requests = importlib.import_module("google.auth.transport.requests")
            verifier = cast(Callable[..., object], getattr(id_token, "verify_firebase_token"))
            request_factory = cast(Callable[[], object], getattr(requests, "Request"))
            claims = verifier(token, request_factory(), audience=self.project_id)
        except Exception as error:  # noqa: BLE001 - auth failures are one public outcome.
            raise AuthenticationError("Firebase ID token verification failed") from error
        if not isinstance(claims, Mapping):
            raise AuthenticationError("Firebase ID token claims are invalid")
        uid = claims.get("uid") or claims.get("sub")
        tenant_id = claims.get("tenant_id")
        email = claims.get("email")
        if not isinstance(uid, str) or not uid.strip():
            raise AuthenticationError("Firebase ID token has no uid")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise AuthenticationError("Firebase ID token has no tenant_id claim")
        if email is not None and not isinstance(email, str):
            raise AuthenticationError("Firebase ID token email claim is invalid")
        return FirebasePrincipal(uid.strip(), tenant_id.strip(), email)
