PYTHON ?= python3.12
LEDGER ?= examples/receipts.jsonl

.PHONY: verify-ledger test typecheck

verify-ledger:
	PYTHONPATH=src $(PYTHON) scripts/verify_ledger.py --ledger "$(LEDGER)"

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

typecheck:
	.venv/bin/mypy --strict src/appeal_core
