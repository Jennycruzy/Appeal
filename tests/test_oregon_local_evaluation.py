from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_oregon_local_evaluation import run_preflight  # noqa: E402


class OregonLocalEvaluationTests(unittest.TestCase):
    def manifest(self, count: int) -> dict[str, object]:
        manifest = json.loads((ROOT / "evidence" / "oregon-acceptance.json").read_text(encoding="utf-8"))
        manifest["artifact"]["sha256"] = "c" * 64
        manifest["scope"]["accepted_local_rows"] = count
        manifest["acceptance"]["accepted_record_count"] = count
        manifest["acceptance"]["accepted_narrative_record_count"] = count
        return manifest

    def input_document(self) -> dict[str, object]:
        return {
            "schema_version": "0.1",
            "status": "local_only_ready_for_appeal_adapter",
            "source_id": "oregon_dfr_iro_case_detail_report",
            "source_workbook": {
                "file_name": "oregon-iro-case-detail-report.xlsx",
                "sha256": "c" * 64,
                "raw_artifact_location": "local_download_only_not_repo",
            },
            "scope": {"record_count": 2, "prior_authorization_claimed": False},
            "records": [
                {
                    "source_case_ref": "a" * 64,
                    "source_row": 2,
                    "review_type": "Standard - 30 Day",
                    "case_category": "General Treatment",
                    "treatment_text": "redacted in test fixture",
                    "regulator_outcome": "upheld_denial",
                    "regulator_outcome_label": "Upheld Denial",
                    "denial_reason": None,
                    "appeal_type": None,
                },
                {
                    "source_case_ref": "b" * 64,
                    "source_row": 3,
                    "review_type": "Expedited - 3 Day",
                    "case_category": "General Surgery",
                    "treatment_text": "redacted in test fixture",
                    "regulator_outcome": "overturned_denial",
                    "regulator_outcome_label": "Overturned Denial",
                    "denial_reason": None,
                    "appeal_type": None,
                },
            ],
        }

    def test_adapter_abstains_without_denial_or_policy_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            input_path = temp / "oregon-input.json"
            manifest_path = temp / "oregon-manifest.json"
            output_path = temp / "report.json"
            input_path.write_text(json.dumps(self.input_document()), encoding="utf-8")
            manifest_path.write_text(json.dumps(self.manifest(2)), encoding="utf-8")

            report = run_preflight(
                input_path,
                manifest_path,
                output_path,
                datetime(2026, 8, 27, tzinfo=UTC),
            )

            self.assertEqual(report["status"], "adapter_preflight_blocked")
            self.assertEqual(report["adapter_preflight"]["cases_seen"], 2)
            self.assertEqual(report["adapter_preflight"]["cases_abstained"], 2)
            self.assertEqual(report["adapter_preflight"]["cases_ready_for_full_appeal"], 0)
            self.assertEqual(report["comparison"]["compared_cases"], 0)
            self.assertEqual(report["evaluation"]["appeal_cases_evaluated"], 0)
            self.assertEqual(report["regulator_outcomes"]["counts"], {"overturned_denial": 1, "upheld_denial": 1})
            serialized = json.dumps(report)
            self.assertNotIn("source_case_ref", serialized)
            self.assertNotIn("treatment_text", serialized)

    def test_populated_denial_reason_is_not_silently_accepted(self) -> None:
        document = self.input_document()
        records = document["records"]
        assert isinstance(records, list)
        records[0] = copy.deepcopy(records[0])
        records[0]["denial_reason"] = "not verified"
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            input_path = temp / "oregon-input.json"
            manifest_path = temp / "oregon-manifest.json"
            input_path.write_text(json.dumps(document), encoding="utf-8")
            manifest_path.write_text(json.dumps(self.manifest(2)), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "populated denial_reason"):
                run_preflight(
                    input_path,
                    manifest_path,
                    temp / "report.json",
                    datetime(2026, 8, 27, tzinfo=UTC),
                )


if __name__ == "__main__":
    unittest.main()
