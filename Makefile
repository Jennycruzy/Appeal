PYTHON ?= python3.12
LEDGER ?= examples/receipts.jsonl
SYNTHETIC_INPUT_DIR ?= .cache/synthea/v4.0.0/full_fixed_20260826_a
HAPI_LOAD_REPORT ?= evidence/hapi-load.json
HAPI_VERIFY_REPORT ?= evidence/hapi-verify.json
HAPI_TIMEOUT ?= 600
HAPI_START_INDEX ?= 1
SYNTHETIC_DISTRIBUTION_REPORT ?= evidence/synthea-distribution.json
NY_DFS_INPUT ?= ../Downloads/peasadata.xlsx
NY_DFS_PRIVACY_REVIEW ?= ../Downloads/ny-dfs-privacy-review.json
NY_DFS_ACCEPTANCE_MANIFEST ?= evidence/ny-dfs-acceptance.json

.PHONY: verify-ledger test typecheck load-hapi verify-hapi inspect-synthea prepare-ny-dfs-review validate-ny-dfs require-ny-dfs-ready

verify-ledger:
	PYTHONPATH=src $(PYTHON) scripts/verify_ledger.py --ledger "$(LEDGER)"

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

typecheck:
	.venv/bin/mypy --strict src/appeal_core

load-hapi:
	PYTHONPATH=src $(PYTHON) scripts/load_synthea_corpus.py --input-dir "$(SYNTHETIC_INPUT_DIR)" --report "$(HAPI_LOAD_REPORT)" --timeout "$(HAPI_TIMEOUT)" --start-index "$(HAPI_START_INDEX)"

verify-hapi:
	PYTHONPATH=src $(PYTHON) scripts/verify_hapi_load.py --report "$(HAPI_VERIFY_REPORT)"

inspect-synthea:
	PYTHONPATH=src $(PYTHON) scripts/inspect_synthea_distribution.py --input-dir "$(SYNTHETIC_INPUT_DIR)" --report "$(SYNTHETIC_DISTRIBUTION_REPORT)"

prepare-ny-dfs-review:
	$(PYTHON) scripts/prepare_ny_dfs_privacy_review.py --xlsx "$(NY_DFS_INPUT)" --output "$(NY_DFS_PRIVACY_REVIEW)"

validate-ny-dfs:
	$(PYTHON) scripts/validate_ny_dfs_acceptance.py --manifest "$(NY_DFS_ACCEPTANCE_MANIFEST)"

require-ny-dfs-ready:
	$(PYTHON) scripts/validate_ny_dfs_acceptance.py --manifest "$(NY_DFS_ACCEPTANCE_MANIFEST)" --xlsx "$(NY_DFS_INPUT)" --require-ready
