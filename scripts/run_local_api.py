"""Run the unauthenticated local Appeal JSON API on loopback."""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

from appeal_agents.workflow import AppealWorkflow
from appeal_core import CaseStateMachine, DeadlineCatalog, ReceiptLedger
from appeal_platform import LocalCaseRuntime
from appeal_service import LocalAppealService, LocalHttpApi


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT.parent / "Downloads" / "appeal-local-api-receipts.jsonl"


def build_api(ledger_path: Path) -> LocalHttpApi:
    deadlines = DeadlineCatalog.from_path(ROOT / "config" / "deadlines.yaml")
    workflow = AppealWorkflow(
        CaseStateMachine(deadlines),
        ledger=ReceiptLedger(ledger_path),
    )
    return LocalHttpApi(
        LocalAppealService(LocalCaseRuntime(workflow)),
        deployment=os.getenv("APPEAL_DEPLOYMENT", "local"),
    )


def serve(host: str, port: int, ledger_path: Path) -> None:
    api = build_api(ledger_path)

    class Handler(BaseHTTPRequestHandler):
        def _respond(self, status: int, value: dict[str, object]) -> None:
            body = json.dumps(value, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            status, value = api.handle("GET", self.path)
            self._respond(status, value)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            if length > 64 * 1024:
                self._respond(413, {"error": "request_too_large"})
                return
            raw = self.rfile.read(length)
            payload: dict[str, object] = {}
            if raw:
                parsed: object = json.loads(raw.decode("utf-8"))
                if not isinstance(parsed, dict):
                    self._respond(400, {"error": "json_object_required"})
                    return
                payload = cast(dict[str, object], parsed)
            status, value = api.handle("POST", self.path, payload)
            self._respond(status, value)

        def log_message(self, format: str, *args: object) -> None:
            return

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Local Appeal API listening on http://{host}:{port}")
    print("Endpoints: GET /healthz; POST /api/demo/cases; GET /api/cases/tenant-demo")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    args = parser.parse_args()
    serve(args.host, args.port, args.ledger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
