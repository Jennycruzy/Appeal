#!/usr/bin/env python3
"""Verify an Appeal receipt ledger and fail on the first integrity error."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from appeal_core import LedgerIntegrityError, ReceiptLedger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = ReceiptLedger(args.ledger).verify()
    except LedgerIntegrityError as error:
        print(f"LEDGER INVALID: {error}")
        return 2
    print(json.dumps({"entry_count": result.entry_count, "tip_hash": result.tip_hash}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
