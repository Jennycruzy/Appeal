"""Run the local event-driven Appeal runtime on a synthetic case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from appeal_agents.demo import demo_input
from appeal_agents.workflow import AppealWorkflow
from appeal_core import CaseStateMachine, DeadlineCatalog, ReceiptLedger
from appeal_platform import LocalCaseRuntime, PayerAdjudicator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT.parent / "Downloads" / "appeal-local-runtime-receipts.jsonl"
DEFAULT_OUTPUT = ROOT.parent / "Downloads" / "appeal-local-runtime-result.json"


def _outside_repository(path: Path) -> None:
    resolved = path.expanduser().resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise ValueError("local runtime output must remain outside the repository")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    _outside_repository(args.ledger)
    _outside_repository(args.output)
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    appeal_input = demo_input()
    assert appeal_input.policy is not None
    deadlines = DeadlineCatalog.from_path(ROOT / "config" / "deadlines.yaml")
    workflow = AppealWorkflow(
        CaseStateMachine(deadlines),
        ledger=ReceiptLedger(args.ledger),
    )
    runtime = LocalCaseRuntime(workflow)
    runtime.spine.subscribe("appeal.workflow.event", "local-observer", lambda event: None)
    runtime.spine.subscribe("payer.determination.received", "local-observer", lambda event: None)
    result = runtime.submit_and_adjudicate(
        appeal_input,
        PayerAdjudicator(appeal_input.policy),
        at=appeal_input.received_at,
    )
    public = result.to_public_json()
    public["platform"] = {
        "case_count": runtime.store.count(),
        "published_event_count": len(runtime.spine.events()),
        "delivery_count": len(runtime.spine.deliver(at=appeal_input.received_at)),
        "memory_record_count": len(runtime.memory.public_records()),
        "reversibility": runtime.reversibility.to_public_json(),
    }
    args.output.write_text(json.dumps(public, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(public, indent=2, sort_keys=True))
    print(f"\nMetadata report: {args.output}")
    print(f"Receipt ledger: {args.ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
