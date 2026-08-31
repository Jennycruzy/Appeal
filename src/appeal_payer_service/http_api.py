"""Framework-free HTTP facade for the payer service."""

from __future__ import annotations

from collections.abc import Mapping

from .service import PayerService


class PayerHttpApi:
    def __init__(self, service: PayerService | None = None) -> None:
        self.service = service or PayerService()

    def handle(self, method: str, path: str, payload: Mapping[str, object] | None = None) -> tuple[int, dict[str, object]]:
        if method.upper() == "GET" and path.rstrip("/") in {"/healthz", "/api/healthz"}:
            return 200, {
                "status": "ok",
                "service": self.service.identity,
                "synthetic_only": True,
                "mutation_authority": False,
                "case_store": False,
            }
        if method.upper() == "POST" and path.rstrip("/") == "/api/payer/determine":
            try:
                return 200, self.service.determine(payload or {})
            except ValueError:
                return 400, {"error": "payer_request_rejected"}
        return 404, {"error": "not_found"}
