"""Framework-free local JSON API over the Appeal case service."""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from collections.abc import Callable, Mapping
from typing import cast
from urllib.parse import unquote

from .service import CaseNotFound, LocalAppealService


class LocalHttpApi:
    """Small HTTP contract used by the local console and future Cloud Run API."""

    def __init__(
        self,
        service: LocalAppealService,
        *,
        deployment: str = "local",
        storage: str = "local",
        security: str = "local_deterministic_fallback",
        scheduler_auth_required: bool = False,
        scheduler_service_account: str | None = None,
        scheduler_audience: str | None = None,
    ) -> None:
        self.service = service
        self.deployment = deployment
        self.storage = storage
        self.security = security
        self.scheduler_auth_required = scheduler_auth_required
        self.scheduler_service_account = scheduler_service_account
        self.scheduler_audience = scheduler_audience

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
        try:
            if method == "GET" and segments in {("healthz",), ("api", "healthz")}:
                return 200, {
                    "status": "ok",
                    "deployment": self.deployment,
                    "storage": self.storage,
                    "security": self.security,
                    "authenticated": False,
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
                return 201, self.service.open_demo_case(
                    at=now,
                    case_id=case_id or "case-demo-001",
                    tenant_id=tenant_id or "tenant-demo",
                    injection=injection,
                    missing_evidence=missing_evidence,
                ).to_public_json()
            if method == "POST" and segments == ("api", "sentinel", "tick"):
                if not self._scheduler_authorized(headers or {}):
                    return 401, {"error": "scheduler_auth_required"}
                return 200, self.service.sentinel_tick(at=now).to_public_json()
            if len(segments) == 3 and segments[:2] == ("api", "cases") and method == "GET":
                board = self.service.board(segments[2])
                return 200, {"cases": list(board), "tenant_id": segments[2]}
            if len(segments) == 4 and segments[:2] == ("api", "cases") and method == "GET":
                tenant_id, case_id = segments[2], segments[3]
                return 200, self.service.get(tenant_id, case_id).to_public_json()
            if len(segments) == 5 and segments[:2] == ("api", "cases") and method == "POST":
                tenant_id, case_id, action = segments[2], segments[3], segments[4]
                # The action is intentionally selected by the route, not by a
                # model or request payload.
                if action == "approve":
                    return 200, self.service.approve(tenant_id, case_id, at=now).to_public_json()
                if action == "adjudicate":
                    return 200, self.service.adjudicate(tenant_id, case_id, at=now).to_public_json()
            return 404, {"error": "not_found"}
        except CaseNotFound:
            return 404, {"error": "not_found"}
        except (KeyError, ValueError):
            return 409, {"error": "case_operation_rejected"}
        except Exception:
            return 500, {"error": "internal_error"}

    def _scheduler_authorized(self, headers: Mapping[str, str]) -> bool:
        if not self.scheduler_auth_required:
            return True
        if not self.scheduler_service_account or not self.scheduler_audience:
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
            claims = verifier(token, request_factory(), audience=self.scheduler_audience)
        except Exception:
            return False
        if not isinstance(claims, Mapping):
            return False
        return claims.get("email") == self.scheduler_service_account
