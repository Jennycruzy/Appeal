"""Run the unauthenticated local Appeal JSON API on loopback."""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

from appeal_agents import LocalSecurityBoundary, ManagedSecurityBoundary
from appeal_agents.demo import demo_input
from appeal_agents.workflow import AppealWorkflow
from appeal_core import CaseStateMachine, DeadlineCatalog, ReceiptLedger
from appeal_platform import (
    CaseStore,
    FirestoreCaseStore,
    FirestoreReceiptLedger,
    FirestoreWorkflowSessionStore,
    FirestoreWorkflowPersistence,
    FirestorePubSubEventSpine,
    FirestoreAgentRuntimeInvocationStore,
    AgentRuntimeSubscriber,
    ManagedAgentRuntimeInvoker,
    LocalCaseRuntime,
)
from appeal_service import LocalAppealService, LocalHttpApi


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT.parent / "Downloads" / "appeal-local-api-receipts.jsonl"


def synthetic_input_resolver(tenant_id: str, case_id: str):
    """Rehydrate only the public synthetic demo fixture after a restart."""

    if not tenant_id.startswith("tenant-demo") or not case_id.startswith("case-demo"):
        return None
    return demo_input(case_id=case_id, tenant_id=tenant_id)


def build_store() -> tuple[CaseStore, str]:
    storage = os.getenv("APPEAL_STORAGE", "local").strip().lower()
    if storage == "local":
        return CaseStore(), storage
    if storage == "firestore":
        return (
            FirestoreCaseStore(
                project=os.getenv("GOOGLE_CLOUD_PROJECT"),
                database=os.getenv("APPEAL_FIRESTORE_DATABASE", "(default)"),
            ),
            storage,
        )
    raise ValueError(f"unsupported APPEAL_STORAGE value: {storage!r}")


def build_security() -> tuple[LocalSecurityBoundary, str]:
    security = os.getenv("APPEAL_SECURITY", "local").strip().lower()
    if security == "local":
        return LocalSecurityBoundary(), "local_deterministic_fallback"
    if security == "managed":
        return (
            ManagedSecurityBoundary(
                project=os.getenv("GOOGLE_CLOUD_PROJECT", ""),
                model_armor_location=os.getenv("APPEAL_MODEL_ARMOR_LOCATION", "europe-west2"),
                model_armor_template=os.getenv("APPEAL_MODEL_ARMOR_TEMPLATE", "appeal-tripwire-v1"),
                gemma_location=os.getenv("APPEAL_GEMMA_LOCATION", "global"),
                gemma_model=os.getenv("APPEAL_GEMMA_MODEL", "google/gemma-4-26b-a4b-it-maas"),
            ),
            "managed_model_armor_gemma",
        )
    raise ValueError(f"unsupported APPEAL_SECURITY value: {security!r}")


def build_api(ledger_path: Path) -> LocalHttpApi:
    deadlines = DeadlineCatalog.from_path(ROOT / "config" / "deadlines.yaml")
    store, storage = build_store()
    security, security_name = build_security()
    session_store = (
        FirestoreWorkflowSessionStore(
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            database=os.getenv("APPEAL_FIRESTORE_DATABASE", "(default)"),
        )
        if storage == "firestore"
        else None
    )
    workflow_persistence = (
        FirestoreWorkflowPersistence(
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            database=os.getenv("APPEAL_FIRESTORE_DATABASE", "(default)"),
        )
        if storage == "firestore"
        else None
    )
    ledger = (
        FirestoreReceiptLedger(
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            database=os.getenv("APPEAL_FIRESTORE_DATABASE", "(default)"),
        )
        if storage == "firestore"
        else ReceiptLedger(ledger_path)
    )
    event_spine_name = os.getenv("APPEAL_EVENT_SPINE", "local").strip().lower()
    event_spine = None
    if event_spine_name == "pubsub":
        if storage != "firestore":
            raise ValueError("Pub/Sub event spine requires Firestore storage")
        event_spine = FirestorePubSubEventSpine(
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            topic=os.getenv("APPEAL_PUBSUB_TOPIC", "appeal-events"),
            database=os.getenv("APPEAL_FIRESTORE_DATABASE", "(default)"),
        )
    elif event_spine_name != "local":
        raise ValueError(f"unsupported APPEAL_EVENT_SPINE value: {event_spine_name!r}")
    workflow = AppealWorkflow(
        CaseStateMachine(deadlines),
        ledger=ledger,
        security=security,
    )
    agent_runtime_resource = os.getenv("APPEAL_AGENT_RUNTIME_RESOURCE", "").strip()
    agent_runtime_subscriber = None
    agent_runtime_name = "disabled"
    if agent_runtime_resource:
        if storage != "firestore":
            raise ValueError("managed Agent Runtime subscriber requires Firestore storage")
        agent_runtime_store = FirestoreAgentRuntimeInvocationStore(
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            database=os.getenv("APPEAL_FIRESTORE_DATABASE", "(default)"),
            claim_lease_seconds=float(os.getenv("APPEAL_AGENT_RUNTIME_CLAIM_LEASE_SECONDS", "120")),
        )
        agent_runtime_subscriber = AgentRuntimeSubscriber(
            ManagedAgentRuntimeInvoker(
                resource_name=agent_runtime_resource,
                project=os.getenv("GOOGLE_CLOUD_PROJECT", ""),
                location=os.getenv("APPEAL_AGENT_RUNTIME_LOCATION", "europe-west2"),
                timeout_seconds=float(os.getenv("APPEAL_AGENT_RUNTIME_TIMEOUT_SECONDS", "120")),
            ),
            agent_runtime_store,
            synthetic_only=os.getenv("APPEAL_AGENT_RUNTIME_SYNTHETIC_ONLY", "true").lower() == "true",
            tenant_prefix=os.getenv("APPEAL_AGENT_RUNTIME_TENANT_PREFIX", "tenant-demo"),
            case_prefix=os.getenv("APPEAL_AGENT_RUNTIME_CASE_PREFIX", "case-demo"),
        )
        agent_runtime_name = "managed_subscriber_synthetic_only"
    return LocalHttpApi(
        LocalAppealService(
            LocalCaseRuntime(
                workflow,
                store=store,
                session_store=session_store,
                spine=event_spine,
                input_resolver=synthetic_input_resolver,
                workflow_persistence=workflow_persistence,
            ),
            agent_runtime_subscriber=agent_runtime_subscriber,
        ),
        deployment=os.getenv("APPEAL_DEPLOYMENT", "local"),
        storage=storage,
        security=security_name,
        event_spine=("pubsub_firestore" if event_spine is not None else "local_in_process"),
        scheduler_auth_required=os.getenv("APPEAL_SCHEDULER_AUTH_REQUIRED", "false").lower() == "true",
        scheduler_service_account=os.getenv("APPEAL_SCHEDULER_SERVICE_ACCOUNT"),
        scheduler_audience=os.getenv("APPEAL_SCHEDULER_AUDIENCE"),
        pubsub_service_account=os.getenv("APPEAL_PUBSUB_PUSH_SERVICE_ACCOUNT"),
        pubsub_audience=os.getenv("APPEAL_PUBSUB_AUDIENCE"),
        agent_runtime=agent_runtime_name,
        firebase_auth_required=os.getenv("APPEAL_FIREBASE_AUTH_REQUIRED", "false").lower() == "true",
        firebase_project_id=(
            os.getenv("APPEAL_FIREBASE_PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", "")).strip()
            or None
        ),
        mobile_link_secret=os.getenv("APPEAL_MOBILE_LINK_SECRET"),
        mobile_link_ttl_seconds=int(os.getenv("APPEAL_MOBILE_LINK_TTL_SECONDS", "900")),
    )


def serve(host: str, port: int, ledger_path: Path) -> None:
    api = build_api(ledger_path)
    allowed_cors_origins = frozenset(
        origin.strip()
        for origin in os.getenv("APPEAL_CORS_ORIGINS", "").split("|")
        if origin.strip()
    )

    class Handler(BaseHTTPRequestHandler):
        def _cors_headers(self) -> dict[str, str]:
            origin = self.headers.get("Origin", "").strip()
            if not origin or origin not in allowed_cors_origins:
                return {}
            return {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Headers": "Authorization, Content-Type",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Max-Age": "600",
                "Vary": "Origin",
            }

        def _respond(self, status: int, value: dict[str, object]) -> None:
            body = json.dumps(value, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for name, value in self._cors_headers().items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            for name, value in self._cors_headers().items():
                self.send_header(name, value)
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            status, value = api.handle("GET", self.path, headers=dict(self.headers.items()))
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
            status, value = api.handle("POST", self.path, payload, headers=dict(self.headers.items()))
            self._respond(status, value)

        def log_message(self, format: str, *args: object) -> None:
            return

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Local Appeal API listening on http://{host}:{port}")
    print("Endpoints: GET /healthz, /api/healthz; POST /api/demo/cases; GET /api/cases/tenant-demo")
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
