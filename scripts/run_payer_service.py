"""Run the stateless synthetic payer service."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

from appeal_payer_service import PayerHttpApi


def serve(host: str, port: int) -> None:
    api = PayerHttpApi()

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
            try:
                value = json.loads(raw.decode("utf-8")) if raw else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._respond(400, {"error": "json_object_required"})
                return
            if not isinstance(value, dict):
                self._respond(400, {"error": "json_object_required"})
                return
            status, response = api.handle("POST", self.path, cast(dict[str, object], value))
            self._respond(status, response)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Payer service listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> int:
    serve("0.0.0.0", int(os.getenv("PORT", "8080")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
