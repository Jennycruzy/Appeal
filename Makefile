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
NY_DFS_PRIVACY_DECISIONS ?= ../Downloads/ny-dfs-privacy-decisions.json
NY_DFS_ACCEPTANCE_MANIFEST ?= evidence/ny-dfs-acceptance.json
OREGON_IRO_INPUT ?= ../Downloads/oregon-iro-case-detail-report.xlsx
OREGON_IRO_REPORT ?= evidence/oregon-iro-acquisition.json
OREGON_IRO_ACCEPTANCE_MANIFEST ?= evidence/oregon-acceptance.json
OREGON_IRO_LOCAL_OUTPUT ?= ../Downloads/oregon-iro-local-evaluation.json
OREGON_IRO_EVALUATION_REPORT ?= evidence/oregon-evaluation.json
DMHC_IMR_INPUT ?= ../Downloads/independent-medical-review-determinations-trends.csv
DMHC_IMR_REPORT ?= evidence/dmhc-imr-acquisition.json

.PHONY: verify-ledger test typecheck load-hapi verify-hapi inspect-synthea prepare-ny-dfs-review review-ny-dfs-privacy validate-ny-dfs require-ny-dfs-ready inspect-dmhc-imr inspect-oregon-iro prepare-oregon-local-evaluation run-oregon-local-evaluation

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

review-ny-dfs-privacy:
	$(PYTHON) scripts/review_ny_dfs_privacy.py --xlsx "$(NY_DFS_INPUT)" --packet "$(NY_DFS_PRIVACY_REVIEW)" --output "$(NY_DFS_PRIVACY_DECISIONS)"

validate-ny-dfs:
	$(PYTHON) scripts/validate_ny_dfs_acceptance.py --manifest "$(NY_DFS_ACCEPTANCE_MANIFEST)"

require-ny-dfs-ready:
	$(PYTHON) scripts/validate_ny_dfs_acceptance.py --manifest "$(NY_DFS_ACCEPTANCE_MANIFEST)" --xlsx "$(NY_DFS_INPUT)" --require-ready

inspect-dmhc-imr:
	$(PYTHON) scripts/inspect_dmhc_imr.py --csv "$(DMHC_IMR_INPUT)" --output "$(DMHC_IMR_REPORT)"

inspect-oregon-iro:
	$(PYTHON) scripts/inspect_oregon_iro.py --xlsx "$(OREGON_IRO_INPUT)" --output "$(OREGON_IRO_REPORT)"

prepare-oregon-local-evaluation:
	$(PYTHON) scripts/prepare_oregon_local_evaluation.py --xlsx "$(OREGON_IRO_INPUT)" --manifest "$(OREGON_IRO_ACCEPTANCE_MANIFEST)" --output "$(OREGON_IRO_LOCAL_OUTPUT)"

run-oregon-local-evaluation:
	PYTHONPATH=src $(PYTHON) scripts/run_oregon_local_evaluation.py --input "$(OREGON_IRO_LOCAL_OUTPUT)" --manifest "$(OREGON_IRO_ACCEPTANCE_MANIFEST)" --output "$(OREGON_IRO_EVALUATION_REPORT)"
