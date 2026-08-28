"""Seed one synthetic expired case for the deployed Deadline Sentinel."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from appeal_core import Actor, ActorKind, Case, CaseState, CaseStateMachine, DecisionSource, DeadlineCatalog, EvidenceRef
from appeal_platform import FirestoreCaseStore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "onyx-yeti-506606-i9")
DEFAULT_OUTPUT = ROOT / "evidence" / "sentinel-seed.json"


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("entered-at must be an ISO-8601 datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("entered-at must include a timezone")
    return parsed.astimezone(UTC)


def _seed(machine: CaseStateMachine, case_id: str, tenant_id: str, entered_at: datetime) -> Case:
    agent = Actor("appeal-seed-agent", ActorKind.AGENT)
    source = DecisionSource("deterministic", "synthetic-sentinel-seed", "0.1")
    case = machine.create(case_id, tenant_id, entered_at, agent, source)
    for state, key in [
        (CaseState.DENIAL_PARSED, "parse"),
        (CaseState.POLICY_LOCATED, "policy"),
        (CaseState.CRITERION_IDENTIFIED, "criterion"),
        (CaseState.EVIDENCE_ASSEMBLED, "evidence"),
        (CaseState.DRAFT_READY, "draft"),
        (CaseState.AWAITING_CLINICIAN, "review"),
    ]:
        case = machine.transition(
            case,
            state,
            entered_at,
            agent,
            source,
            "synthetic Deadline Sentinel fixture",
            (),
            f"{case_id}:{key}",
        )
    signature = EvidenceRef("ClinicianSignature", f"signature://{case_id}/1", "a" * 64)
    case = machine.transition(
        case,
        CaseState.SUBMITTED_LEVEL_1,
        entered_at,
        Actor("appeal-seed-clinician", ActorKind.HUMAN),
        DecisionSource("human", "synthetic-sentinel-seed", "0.1"),
        "synthetic Deadline Sentinel fixture",
        (),
        f"{case_id}:submit",
        signature,
    )
    return machine.transition(
        case,
        CaseState.AWAITING_DETERMINATION,
        entered_at,
        Actor("appeal-seed-submission-gate", ActorKind.SYSTEM),
        source,
        "synthetic Deadline Sentinel fixture",
        (),
        f"{case_id}:await",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--tenant-id", default="tenant-sentinel-demo")
    parser.add_argument("--case-id", default="case-sentinel-expired-001")
    parser.add_argument("--entered-at", default="2026-08-18T12:00:00Z")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    machine = CaseStateMachine(DeadlineCatalog.from_path(ROOT / "config" / "deadlines.yaml"))
    store = FirestoreCaseStore(project=args.project)
    if store.get(args.tenant_id, args.case_id) is not None:
        raise ValueError("the requested sentinel fixture already exists")
    case = _seed(machine, args.case_id, args.tenant_id, _parse_datetime(args.entered_at))
    store.save(case)
    report = {
        "schema_version": "0.1",
        "project_id": args.project,
        "database": "(default)",
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "state": case.state.value,
        "entered_at": case.entered_at.isoformat().replace("+00:00", "Z"),
        "deadline_key": case.deadline_key,
        "synthetic_only": True,
        "raw_content_persisted": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
