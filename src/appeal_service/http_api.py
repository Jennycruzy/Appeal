"""Framework-free local JSON API over the Appeal case service."""

from __future__ import annotations

import base64
import importlib
import json
import logging
from datetime import UTC, datetime
from collections.abc import Callable, Mapping
from typing import cast
from urllib.parse import unquote

from appeal_platform import DomainEvent, default_agent_registry

from .approval_links import ApprovalLink, ApprovalLinkError, ApprovalLinkSigner
from .auth import AuthenticationError, FirebaseIdTokenVerifier, PrincipalVerifier
from .service import CaseNotFound, LocalAppealService


_LOGGER = logging.getLogger(__name__)


class LocalHttpApi:
    """Small HTTP contract used by the local console and future Cloud Run API."""

    def __init__(
        self,
        service: LocalAppealService,
        *,
        deployment: str = "local",
        storage: str = "local",
        event_spine: str = "local_in_process",
        security: str = "local_deterministic_fallback",
        scheduler_auth_required: bool = False,
        scheduler_service_account: str | None = None,
        scheduler_audience: str | None = None,
        pubsub_service_account: str | None = None,
        pubsub_audience: str | None = None,
        agent_runtime: str = "disabled",
        firebase_auth_required: bool = False,
        firebase_project_id: str | None = None,
        firebase_verifier: PrincipalVerifier | None = None,
        mobile_link_secret: str | None = None,
        mobile_link_ttl_seconds: int = 900,
    ) -> None:
        self.service = service
        self.deployment = deployment
        self.storage = storage
        self.event_spine = event_spine
        self.security = security
        self.scheduler_auth_required = scheduler_auth_required
        self.scheduler_service_account = scheduler_service_account
        self.scheduler_audience = scheduler_audience
        self.pubsub_service_account = pubsub_service_account
        self.pubsub_audience = pubsub_audience
        self.agent_runtime = agent_runtime
        self.firebase_auth_required = firebase_auth_required
        self.firebase_verifier = firebase_verifier
        if self.firebase_verifier is None and firebase_project_id:
            self.firebase_verifier = FirebaseIdTokenVerifier(firebase_project_id)
        self.mobile_link_signer = (
            ApprovalLinkSigner(mobile_link_secret, ttl_seconds=mobile_link_ttl_seconds)
            if mobile_link_secret
            else None
        )

    def handle(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
        *,
        at: datetime | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, object]]:
        method = method.upper()
        segments = tuple(unquote(segment) for segment in path.split("/") if segment)
        now = (at or datetime.now(UTC)).astimezone(UTC)
        request_headers = headers or {}
        try:
            if method == "GET" and segments in {("healthz",), ("api", "healthz")}:
                return 200, {
                    "status": "ok",
                    "deployment": self.deployment,
                    "storage": self.storage,
                    "event_spine": self.event_spine,
                    "security": self.security,
                    "agent_runtime": self.agent_runtime,
                    "authenticated": self.firebase_auth_required,
                    "auth_mode": "firebase_id_token" if self.firebase_auth_required else "none",
                    "mobile_approval": self.mobile_link_signer is not None,
                }
            if method == "POST" and segments == ("api", "demo", "cases"):
                case_id = payload.get("case_id") if payload is not None else None
                tenant_id = payload.get("tenant_id") if payload is not None else None
                injection = payload.get("injection", False) if payload is not None else False
                missing_evidence = payload.get("missing_evidence", False) if payload is not None else False
                if case_id is not None and not isinstance(case_id, str):
                    raise ValueError("demo case_id must be a string")
                if tenant_id is not None and not isinstance(tenant_id, str):
                    raise ValueError("demo tenant_id must be a string")
                if not isinstance(injection, bool) or not isinstance(missing_evidence, bool):
                    raise ValueError("demo safety flags must be boolean")
                requested_tenant = tenant_id or "tenant-demo"
                denied = self._authorize_tenant(request_headers, requested_tenant)
                if denied is not None:
                    return denied
                return 201, self.service.open_demo_case(
                    at=now,
                    case_id=case_id or "case-demo-001",
                    tenant_id=requested_tenant,
                    injection=injection,
                    missing_evidence=missing_evidence,
                ).to_public_json()
            if method == "POST" and segments == ("api", "sentinel", "tick"):
                if not self._scheduler_authorized(request_headers):
                    return 401, {"error": "scheduler_auth_required"}
                return 200, self.service.sentinel_tick(at=now).to_public_json()
            if method == "POST" and segments == ("api", "events", "pubsub"):
                if not self._pubsub_authorized(request_headers):
                    return 401, {"error": "pubsub_auth_required"}
                try:
                    event = self._event_from_push(payload or {})
                except ValueError as error:
                    # Keep diagnostics aggregate-only. The event body can
                    # contain tenant-scoped identifiers, so never log it or
                    # the parser message in a hosted request.
                    _LOGGER.warning(
                        "reference_only_pubsub_event_rejected error_type=%s",
                        type(error).__name__,
                    )
                    raise
                return 200, self.service.accept_event(event)
            if method == "GET" and len(segments) == 3 and segments[:2] == ("api", "agents"):
                role = segments[2]
                try:
                    registration = default_agent_registry().for_role(role)
                except KeyError:
                    return 404, {"error": "agent_not_found"}
                result = registration.to_json()
                result.update(
                    {
                        "live": True,
                        "synthetic_only": True,
                        "endpoint_path": f"/api/agents/{role}",
                    }
                )
                return 200, result
            if len(segments) == 3 and segments[:2] == ("api", "cases") and method == "GET":
                denied = self._authorize_tenant(request_headers, segments[2])
                if denied is not None:
                    return denied
                board = self.service.board(segments[2])
                return 200, {"cases": list(board), "tenant_id": segments[2]}
            if len(segments) == 4 and segments[:2] == ("api", "cases") and method == "GET":
                tenant_id, case_id = segments[2], segments[3]
                denied = self._authorize_tenant(request_headers, tenant_id)
                if denied is not None:
                    return denied
                return 200, self.service.get(tenant_id, case_id).to_public_json()
            if len(segments) == 5 and segments[:2] == ("api", "cases") and method == "POST":
                tenant_id, case_id, action = segments[2], segments[3], segments[4]
                denied = self._authorize_tenant(request_headers, tenant_id)
                if denied is not None:
                    return denied
                # The action is intentionally selected by the route, not by a
                # model or request payload.
                if action == "approve":
                    return 200, self.service.approve(tenant_id, case_id, at=now).to_public_json()
                if action == "adjudicate":
                    return 200, self.service.adjudicate(tenant_id, case_id, at=now).to_public_json()
                if action == "approval-link":
                    if self.mobile_link_signer is None:
                        return 503, {"error": "mobile_approval_unconfigured"}
                    forced_denial = self._authorize_tenant(request_headers, tenant_id, force=True)
                    if forced_denial is not None:
                        return forced_denial
                    current_case = self.service.get(tenant_id, case_id)
                    if current_case.to_public_json().get("case_state") != "AWAITING_CLINICIAN":
                        return 409, {"error": "clinician_approval_not_pending"}
                    token = self.mobile_link_signer.issue(tenant_id, case_id, now=now)
                    expires_at = now.timestamp() + self.mobile_link_signer.ttl_seconds
                    return 201, {
                        "approval_link": token,
                        "expires_at": datetime.fromtimestamp(expires_at, tz=UTC).isoformat().replace("+00:00", "Z"),
                        "tenant_id": tenant_id,
                        "case_id": case_id,
                    }
            if len(segments) == 4 and segments[:3] == ("api", "mobile", "approval"):
                token = segments[3]
                link, link_error = self._verified_mobile_link(token, now)
                if link_error is not None:
                    return link_error
                assert link is not None
                denied = self._authorize_tenant(request_headers, link.tenant_id)
                if denied is not None:
                    return denied
                if method == "GET":
                    current_public = self.service.get(link.tenant_id, link.case_id).to_public_json()
                    return 200, {
                        "status": "ok",
                        "tenant_id": link.tenant_id,
                        "case_id": link.case_id,
                        "case_state": current_public.get("case_state"),
                        "expires_at": link.expires_at.isoformat().replace("+00:00", "Z"),
                    }
                if method == "POST":
                    decision = payload.get("decision") if payload is not None else None
                    if decision != "approve":
                        return 409, {"error": "approval_decision_required"}
                    return 200, self.service.approve(link.tenant_id, link.case_id, at=now).to_public_json()
            return 404, {"error": "not_found"}
        except CaseNotFound:
            return 404, {"error": "not_found"}
        except (KeyError, ValueError):
            return 409, {"error": "case_operation_rejected"}
        except Exception:
            return 500, {"error": "internal_error"}

    def _authorize_tenant(
        self,
        headers: Mapping[str, str],
        tenant_id: str,
        *,
        force: bool = False,
    ) -> tuple[int, dict[str, object]] | None:
        if not (self.firebase_auth_required or force):
            return None
        if self.firebase_verifier is None:
            return 503, {"error": "firebase_auth_unconfigured"}
        try:
            principal = self.firebase_verifier.verify(headers)
        except AuthenticationError:
            return 401, {"error": "authenticated_user_required"}
        if principal.tenant_id != tenant_id:
            return 403, {"error": "tenant_access_denied"}
        return None

    def _verified_mobile_link(
        self,
        token: str,
        now: datetime,
    ) -> tuple[ApprovalLink | None, tuple[int, dict[str, object]] | None]:
        if self.mobile_link_signer is None:
            return None, (503, {"error": "mobile_approval_unconfigured"})
        try:
            return self.mobile_link_signer.verify(token, now=now), None
        except ApprovalLinkError:
            return None, (401, {"error": "approval_link_invalid"})

    def _scheduler_authorized(self, headers: Mapping[str, str]) -> bool:
        if not self.scheduler_auth_required:
            return True
        return self._service_account_authorized(
            headers,
            self.scheduler_service_account,
            self.scheduler_audience,
        )

    def _pubsub_authorized(self, headers: Mapping[str, str]) -> bool:
        return self._service_account_authorized(
            headers,
            self.pubsub_service_account,
            self.pubsub_audience,
        )

    @staticmethod
    def _service_account_authorized(
        headers: Mapping[str, str],
        expected_service_account: str | None,
        expected_audience: str | None,
    ) -> bool:
        if not expected_service_account or not expected_audience:
            return False
        authorization = next(
            (value for key, value in headers.items() if key.lower() == "authorization"),
            "",
        )
        if not authorization.startswith("Bearer "):
            return False
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            return False
        try:
            id_token = importlib.import_module("google.oauth2.id_token")
            requests = importlib.import_module("google.auth.transport.requests")
            verifier = cast(Callable[..., object], getattr(id_token, "verify_oauth2_token"))
            request_factory = cast(Callable[[], object], getattr(requests, "Request"))
            claims = verifier(token, request_factory(), audience=expected_audience)
        except Exception:
            return False
        if not isinstance(claims, Mapping):
            return False
        return claims.get("email") == expected_service_account

    @staticmethod
    def _event_from_push(payload: Mapping[str, object]) -> DomainEvent:
        message = payload.get("message")
        if isinstance(message, Mapping):
            encoded = message.get("data")
            if not isinstance(encoded, str) or not encoded:
                raise ValueError("Pub/Sub push data is required")
            try:
                raw = base64.b64decode(encoded, validate=True)
                decoded: object = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("Pub/Sub push data must contain a valid event JSON object") from error
        else:
            # Pub/Sub can be configured with noWrapper, in which case the
            # authenticated request body is the reference-only event itself.
            # Supporting both forms keeps the contract aligned with the
            # subscription setting without accepting unvalidated content.
            decoded = payload
        if not isinstance(decoded, Mapping):
            raise ValueError("Pub/Sub event must be a JSON object")
        return DomainEvent.from_json(decoded)
