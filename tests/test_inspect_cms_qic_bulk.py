from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from inspect_cms_qic import PART_D_FIELDS  # noqa: E402
from inspect_cms_qic_bulk import inspect  # noqa: E402


class CmsQicBulkInspectorTests(unittest.TestCase):
    def write_csv(self, path: Path, rows: list[dict[str, str]]) -> None:
        fieldnames = sorted(PART_D_FIELDS)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_streaming_report_keeps_hashed_privacy_locators_only(self) -> None:
        private_value = "member ID 12345 at 10 Main Street"
        row = {field: "value" for field in PART_D_FIELDS}
        row["record_number"] = "QIC-17"
        row["decision_rationale"] = private_value

        with TemporaryDirectory() as directory:
            input_path = Path(directory) / "part-d.csv"
            self.write_csv(input_path, [row])
            report = inspect(
                input_path,
                part="part_d",
                source_url="https://downloads.cms.gov/qic/partd.csv",
                source_etag='"etag"',
                expected_record_count=1,
            )

        serialized = json.dumps(report)
        self.assertEqual(report["status"], "privacy_candidates_require_human_review")
        self.assertEqual(report["inspection"]["rows_scanned"], 1)
        self.assertEqual(report["privacy_scan"]["candidate_locator_count"], 1)
        self.assertEqual(
            report["privacy_scan"]["candidate_counts"],
            {"member_id_label": 1, "physical_address_shape": 1},
        )
        self.assertNotIn(private_value, serialized)
        self.assertNotIn("QIC-17", serialized)
        self.assertFalse(report["acceptance"]["accepted_for_local_evaluation"])

    def test_clean_scan_records_schema_and_count_without_accepting_rows(self) -> None:
        row = {field: "value" for field in PART_D_FIELDS}
        row["record_number"] = "QIC-18"

        with TemporaryDirectory() as directory:
            input_path = Path(directory) / "part-d.csv"
            self.write_csv(input_path, [row, row | {"record_number": "QIC-19"}])
            report = inspect(
                input_path,
                part="part_d",
                source_url="https://downloads.cms.gov/qic/partd.csv",
                source_etag=None,
                expected_record_count=2,
            )

        self.assertEqual(report["status"], "privacy_scan_complete_no_candidates")
        self.assertTrue(report["inspection"]["schema_valid"])
        self.assertTrue(report["inspection"]["record_count_matches_expected"])
        self.assertEqual(report["privacy_scan"]["candidate_locator_count"], 0)
        self.assertEqual(report["acceptance"]["accepted_record_count"], 0)

    def test_malformed_rows_keep_schema_gate_closed(self) -> None:
        with TemporaryDirectory() as directory:
            input_path = Path(directory) / "part-d.csv"
            input_path.write_text("record_number,decision\n1,upheld,extra\n", encoding="utf-8")
            report = inspect(
                input_path,
                part="part_d",
                source_url="https://downloads.cms.gov/qic/partd.csv",
                source_etag=None,
                expected_record_count=1,
            )

        self.assertEqual(report["status"], "bulk_inspection_blocked_schema_or_count")
        self.assertEqual(report["inspection"]["malformed_rows"], 1)
        self.assertFalse(report["inspection"]["schema_valid"])
        self.assertFalse(report["acceptance"]["accepted_for_local_evaluation"])

    def test_bulk_header_aliases_are_explicit_but_missing_record_id_stays_blocked(self) -> None:
        headers = [
            "Part",
            "Decision_Date",
            "Decision_Date_Sortable",
            "Decision",
            "Appeal_Type",
            "Condition",
            "Drug",
            "Decision_Rationale",
            "Coverage_Rules",
        ]
        with TemporaryDirectory() as directory:
            input_path = Path(directory) / "part-d.csv"
            with input_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=headers)
                writer.writeheader()
                writer.writerow({field: "value" for field in headers})
            report = inspect(
                input_path,
                part="part_d",
                source_url="https://downloads.cms.gov/qic/partd.csv",
                source_etag=None,
                expected_record_count=1,
            )

        self.assertEqual(report["inspection"]["missing_expected_fields"], ["record_number"])
        self.assertEqual(report["inspection"]["unexpected_fields"], [])
        self.assertEqual(report["inspection"]["field_mapping"]["Appeal_Type"], "appeal_type")
        self.assertFalse(report["inspection"]["schema_valid"])


if __name__ == "__main__":
    unittest.main()
