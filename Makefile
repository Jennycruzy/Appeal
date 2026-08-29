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
CMS_QIC_REPORT ?= evidence/cms-qic-decision-search.json
CMS_QIC_ACA ?=
CMS_QIC_PART ?= part_d
CMS_QIC_LOCAL_OUTPUT ?= ../Downloads/cms-qic-$(CMS_QIC_PART)-summary.jsonl
CMS_QIC_LOCAL_MANIFEST ?= ../Downloads/cms-qic-$(CMS_QIC_PART)-summary.manifest.json
CMS_QIC_EVALUATION_REPORT ?= evidence/cms-qic-summary-evaluation.json
CMS_QIC_PRIVACY_SCAN_REPORT ?= evidence/cms-qic-$(CMS_QIC_PART)-privacy-scan.json
CMS_QIC_BULK_INPUT ?= ../Downloads/cms-qic-partd-2026-08-25.csv
CMS_QIC_BULK_REPORT ?= evidence/cms-qic-part-d-bulk-inspection.json
CMS_QIC_BULK_SOURCE_URL ?= https://downloads.cms.gov/qic-decision-search/partd-2026-08-25.csv
CMS_QIC_BULK_SOURCE_ETAG ?=
CMS_QIC_BULK_EXPECTED_COUNT ?= 240958
CMS_QIC_BULK_PRIVACY_DECISIONS ?= ../Downloads/cms-qic-partd-privacy-decisions.json
CMS_QIC_BULK_PRIVACY_PROPOSAL ?= ../Downloads/cms-qic-partd-privacy-decisions-agent-proposed.json
CMS_QIC_BULK_ACCEPTANCE_MANIFEST ?= evidence/cms-qic-part-d-bulk-acceptance.json
LOCAL_WORKFLOW_LEDGER ?= ../Downloads/appeal-local-receipts-v0.2.jsonl
LOCAL_WORKFLOW_OUTPUT ?= ../Downloads/appeal-local-workflow-result.json
LOCAL_RUNTIME_LEDGER ?= ../Downloads/appeal-local-runtime-receipts.jsonl
LOCAL_RUNTIME_OUTPUT ?= ../Downloads/appeal-local-runtime-result.json
LOCAL_API_LEDGER ?= ../Downloads/appeal-local-api-receipts.jsonl
MODEL_ARMOR_PROJECT ?= onyx-yeti-506606-i9
MODEL_ARMOR_LOCATION ?= europe-west2
MODEL_ARMOR_TEMPLATE ?= appeal-tripwire-v1
MODEL_ARMOR_OUTPUT ?= evidence/model-armor-measurement.json
GEMMA_PROJECT ?= onyx-yeti-506606-i9
GEMMA_LOCATION ?= global
GEMMA_MODEL ?= google/gemma-4-26b-a4b-it-maas
GEMMA_OUTPUT ?= evidence/gemma-tripwire-measurement.json
CLOUD_RUN_PROJECT ?= onyx-yeti-506606-i9
CLOUD_RUN_REGION ?= europe-west2
CLOUD_RUN_SERVICE ?= appeal-backend
CLOUD_RUN_SERVICE_ACCOUNT ?= appeal-backend@onyx-yeti-506606-i9.iam.gserviceaccount.com
CLOUD_RUN_STORAGE ?= firestore
CLOUD_RUN_FIRESTORE_DATABASE ?= (default)
CLOUD_RUN_EVENT_SPINE ?= pubsub
CLOUD_RUN_PUBSUB_TOPIC ?= appeal-events
CLOUD_RUN_PUBSUB_PUSH_SERVICE_ACCOUNT ?= appeal-pubsub-push@onyx-yeti-506606-i9.iam.gserviceaccount.com
CLOUD_RUN_PUBSUB_AUDIENCE ?= https://appeal-backend-835653516606.europe-west2.run.app/api/events/pubsub
CLOUD_RUN_SECURITY ?= managed
CLOUD_RUN_SCHEDULER_URL ?= https://appeal-backend-835653516606.europe-west2.run.app
CLOUD_RUN_SCHEDULER_SERVICE_ACCOUNT ?= appeal-scheduler@onyx-yeti-506606-i9.iam.gserviceaccount.com
ADK_PROJECT ?= onyx-yeti-506606-i9
ADK_LOCATION ?= global
ADK_MODEL ?= gemini-3.7-flash
ADK_OUTPUT ?= evidence/adk-stage-b-case-exit.json
ADK_LEDGER ?= ../Downloads/appeal-adk-stage-b-receipts.jsonl
SENTINEL_PROJECT ?= onyx-yeti-506606-i9
SENTINEL_TENANT ?= tenant-sentinel-demo
SENTINEL_CASE ?= case-sentinel-expired-001
SENTINEL_ENTERED_AT ?= 2026-08-18T12:00:00Z
SENTINEL_SEED_OUTPUT ?= evidence/sentinel-seed.json

.PHONY: verify-ledger test typecheck run-local-workflow run-local-runtime measure-local-security measure-model-armor measure-gemma run-adk-case run-local-api deploy-cloud-run seed-sentinel-case load-hapi verify-hapi inspect-synthea prepare-ny-dfs-review review-ny-dfs-privacy validate-ny-dfs require-ny-dfs-ready inspect-dmhc-imr inspect-cms-qic fetch-cms-qic-summary run-cms-qic-summary scan-cms-qic-privacy inspect-cms-qic-bulk review-cms-qic-bulk propose-cms-qic-bulk accept-cms-qic-bulk inspect-oregon-iro prepare-oregon-local-evaluation run-oregon-local-evaluation

verify-ledger:
	PYTHONPATH=src $(PYTHON) scripts/verify_ledger.py --ledger "$(LEDGER)"

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

typecheck:
	.venv/bin/mypy --strict src/appeal_core src/appeal_agents src/appeal_platform src/appeal_service

run-local-workflow:
	PYTHONPATH=src $(PYTHON) scripts/run_local_workflow.py --ledger "$(LOCAL_WORKFLOW_LEDGER)" --output "$(LOCAL_WORKFLOW_OUTPUT)"

run-local-runtime:
	PYTHONPATH=src $(PYTHON) scripts/run_local_runtime.py --ledger "$(LOCAL_RUNTIME_LEDGER)" --output "$(LOCAL_RUNTIME_OUTPUT)"

measure-local-security:
	PYTHONPATH=src $(PYTHON) scripts/measure_local_security.py

measure-model-armor:
	GOOGLE_CLOUD_PROJECT="$(MODEL_ARMOR_PROJECT)" PYTHONPATH=src .venv/bin/python scripts/measure_model_armor.py --location "$(MODEL_ARMOR_LOCATION)" --template-id "$(MODEL_ARMOR_TEMPLATE)" --output "$(MODEL_ARMOR_OUTPUT)"

measure-gemma:
	GOOGLE_CLOUD_PROJECT="$(GEMMA_PROJECT)" PYTHONPATH=src .venv/bin/python scripts/measure_gemma.py --project "$(GEMMA_PROJECT)" --location "$(GEMMA_LOCATION)" --model "$(GEMMA_MODEL)" --output "$(GEMMA_OUTPUT)"

run-adk-case:
	GOOGLE_CLOUD_PROJECT="$(ADK_PROJECT)" GOOGLE_CLOUD_LOCATION="$(ADK_LOCATION)" GOOGLE_GENAI_USE_VERTEXAI=TRUE PYTHONPATH=src .venv/bin/python scripts/run_adk_case.py --project "$(ADK_PROJECT)" --location "$(ADK_LOCATION)" --model "$(ADK_MODEL)" --output "$(ADK_OUTPUT)" --ledger "$(ADK_LEDGER)"

run-local-api:
	PYTHONPATH=src $(PYTHON) scripts/run_local_api.py --ledger "$(LOCAL_API_LEDGER)"

deploy-cloud-run:
	gcloud run deploy "$(CLOUD_RUN_SERVICE)" --source . --project "$(CLOUD_RUN_PROJECT)" --region "$(CLOUD_RUN_REGION)" --service-account "$(CLOUD_RUN_SERVICE_ACCOUNT)" --set-env-vars "APPEAL_DEPLOYMENT=cloud_run,APPEAL_STORAGE=$(CLOUD_RUN_STORAGE),APPEAL_EVENT_SPINE=$(CLOUD_RUN_EVENT_SPINE),APPEAL_PUBSUB_TOPIC=$(CLOUD_RUN_PUBSUB_TOPIC),APPEAL_PUBSUB_PUSH_SERVICE_ACCOUNT=$(CLOUD_RUN_PUBSUB_PUSH_SERVICE_ACCOUNT),APPEAL_PUBSUB_AUDIENCE=$(CLOUD_RUN_PUBSUB_AUDIENCE),APPEAL_SECURITY=$(CLOUD_RUN_SECURITY),GOOGLE_CLOUD_PROJECT=$(CLOUD_RUN_PROJECT),APPEAL_FIRESTORE_DATABASE=$(CLOUD_RUN_FIRESTORE_DATABASE),APPEAL_MODEL_ARMOR_LOCATION=$(MODEL_ARMOR_LOCATION),APPEAL_MODEL_ARMOR_TEMPLATE=$(MODEL_ARMOR_TEMPLATE),APPEAL_GEMMA_LOCATION=$(GEMMA_LOCATION),APPEAL_GEMMA_MODEL=$(GEMMA_MODEL),APPEAL_SCHEDULER_AUTH_REQUIRED=true,APPEAL_SCHEDULER_SERVICE_ACCOUNT=$(CLOUD_RUN_SCHEDULER_SERVICE_ACCOUNT),APPEAL_SCHEDULER_AUDIENCE=$(CLOUD_RUN_SCHEDULER_URL)" --allow-unauthenticated --min 0 --max 1 --memory 512Mi --cpu 1 --timeout 300 --quiet

seed-sentinel-case:
	GOOGLE_CLOUD_PROJECT="$(SENTINEL_PROJECT)" PYTHONPATH=src .venv/bin/python scripts/seed_sentinel_case.py --project "$(SENTINEL_PROJECT)" --tenant-id "$(SENTINEL_TENANT)" --case-id "$(SENTINEL_CASE)" --entered-at "$(SENTINEL_ENTERED_AT)" --output "$(SENTINEL_SEED_OUTPUT)"

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

inspect-cms-qic:
	APPEAL_CMS_QIC_ACA="$(CMS_QIC_ACA)" $(PYTHON) scripts/inspect_cms_qic.py --output "$(CMS_QIC_REPORT)"

fetch-cms-qic-summary:
	APPEAL_CMS_QIC_ACA="$(CMS_QIC_ACA)" PYTHONPATH=scripts $(PYTHON) scripts/fetch_cms_qic_summary.py --part "$(CMS_QIC_PART)" --output "$(CMS_QIC_LOCAL_OUTPUT)" --manifest "$(CMS_QIC_LOCAL_MANIFEST)" --all

run-cms-qic-summary:
	PYTHONPATH=src:scripts $(PYTHON) scripts/run_cms_qic_summary_evaluation.py --input "$(CMS_QIC_LOCAL_OUTPUT)" --manifest "$(CMS_QIC_LOCAL_MANIFEST)" --output "$(CMS_QIC_EVALUATION_REPORT)"

scan-cms-qic-privacy:
	APPEAL_CMS_QIC_ACA="$(CMS_QIC_ACA)" PYTHONPATH=scripts $(PYTHON) scripts/scan_cms_qic_privacy.py --part "$(CMS_QIC_PART)" --output "$(CMS_QIC_PRIVACY_SCAN_REPORT)"

inspect-cms-qic-bulk:
	PYTHONPATH=scripts $(PYTHON) scripts/inspect_cms_qic_bulk.py --part "$(CMS_QIC_PART)" --csv "$(CMS_QIC_BULK_INPUT)" --output "$(CMS_QIC_BULK_REPORT)" --source-url "$(CMS_QIC_BULK_SOURCE_URL)" --source-etag "$(CMS_QIC_BULK_SOURCE_ETAG)" --expected-record-count "$(CMS_QIC_BULK_EXPECTED_COUNT)"

review-cms-qic-bulk:
	PYTHONPATH=scripts $(PYTHON) scripts/review_cms_qic_bulk_privacy.py --csv "$(CMS_QIC_BULK_INPUT)" --report "$(CMS_QIC_BULK_REPORT)" --output "$(CMS_QIC_BULK_PRIVACY_DECISIONS)"

propose-cms-qic-bulk:
	PYTHONPATH=scripts $(PYTHON) scripts/propose_cms_qic_bulk_privacy.py --csv "$(CMS_QIC_BULK_INPUT)" --report "$(CMS_QIC_BULK_REPORT)" --output "$(CMS_QIC_BULK_PRIVACY_PROPOSAL)"

accept-cms-qic-bulk:
	PYTHONPATH=scripts $(PYTHON) scripts/accept_cms_qic_bulk.py --csv "$(CMS_QIC_BULK_INPUT)" --report "$(CMS_QIC_BULK_REPORT)" --proposal "$(CMS_QIC_BULK_PRIVACY_PROPOSAL)" --output "$(CMS_QIC_BULK_ACCEPTANCE_MANIFEST)"

inspect-oregon-iro:
	$(PYTHON) scripts/inspect_oregon_iro.py --xlsx "$(OREGON_IRO_INPUT)" --output "$(OREGON_IRO_REPORT)"

prepare-oregon-local-evaluation:
	$(PYTHON) scripts/prepare_oregon_local_evaluation.py --xlsx "$(OREGON_IRO_INPUT)" --manifest "$(OREGON_IRO_ACCEPTANCE_MANIFEST)" --output "$(OREGON_IRO_LOCAL_OUTPUT)"

run-oregon-local-evaluation:
	PYTHONPATH=src $(PYTHON) scripts/run_oregon_local_evaluation.py --input "$(OREGON_IRO_LOCAL_OUTPUT)" --manifest "$(OREGON_IRO_ACCEPTANCE_MANIFEST)" --output "$(OREGON_IRO_EVALUATION_REPORT)"
