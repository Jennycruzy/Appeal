"""Run the local seven-agent Appeal workflow on a synthetic case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from appeal_agents.demo import demo_input
from appeal_agents.workflow import AppealWorkflow
from appeal_core import CaseStateMachine, DeadlineCatalog, ReceiptLedger


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT.parent / "Downloads" / "appeal-local-receipts-v0.2.jsonl"
DEFAULT_OUTPUT = ROOT.parent / "Downloads" / "appeal-local-workflow-result.json"


def _outside_repository(path: Path) -> None:
    resolved = path.expanduser().resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise ValueError("local workflow output must remain outside the repository")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve", action="store_true", help="simulate the clinician co-signature")
    parser.add_argument("--inject", action="store_true", help="include a synthetic prompt-injection attack")
    parser.add_argument("--missing-evidence", action="store_true", help="omit one required chart observation")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    _outside_repository(args.ledger)
    _outside_repository(args.output)
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    deadlines = DeadlineCatalog.from_path(ROOT / "config" / "deadlines.yaml")
    workflow = AppealWorkflow(CaseStateMachine(deadlines), ledger=ReceiptLedger(args.ledger))
    result = workflow.run(
        demo_input(injection=args.inject, missing_evidence=args.missing_evidence),
        clinician_decision=True if args.approve else None,
    )
    public = result.to_public_json()
    args.output.write_text(json.dumps(public, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(public, indent=2, sort_keys=True))
    if result.draft is not None:
        print("\n--- synthetic draft (in memory; not written to the report) ---")
        print(result.draft.text)
    print(f"\nMetadata report: {args.output}")
    print(f"Receipt ledger: {args.ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
