"""Framework-free local JSON API over the Appeal case service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Mapping
from urllib.parse import unquote

from .service import CaseNotFound, LocalAppealService


class LocalHttpApi:
    """Small HTTP contract used by the local console and future Cloud Run API."""

    def __init__(self, service: LocalAppealService, *, deployment: str = "local") -> None:
        self.service = service
        self.deployment = deployment

    def handle(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
        *,
        at: datetime | None = None,
    ) -> tuple[int, dict[str, object]]:
        method = method.upper()
        segments = tuple(unquote(segment) for segment in path.split("/") if segment)
        now = (at or datetime.now(UTC)).astimezone(UTC)
        try:
            if method == "GET" and segments == ("healthz",):
                return 200, {
                    "status": "ok",
                    "deployment": self.deployment,
                    "authenticated": False,
                }
            if method == "POST" and segments == ("api", "demo", "cases"):
                return 201, self.service.open_demo_case(at=now).to_public_json()
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
