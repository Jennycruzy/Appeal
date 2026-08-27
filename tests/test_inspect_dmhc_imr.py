from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from inspect_dmhc_imr import inspect  # noqa: E402


class DmhcInspectorTests(unittest.TestCase):
    def test_report_is_aggregate_only_and_keeps_gates_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "imr.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=["Case Number", "Determination", "Findings", "Treatment"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "Case Number": "MN22-37709",
                        "Determination": "Overturned",
                        "Findings": "DOB: 01/02/1980; member id: ABC123; 10 Main Street",
                        "Treatment": "redacted treatment",
                    }
                )
            report = inspect(path)

            self.assertEqual(report["inspection"]["data_rows"], 1)
            self.assertTrue(report["inspection"]["findings_field_present"])
            self.assertEqual(report["gates"]["prior_authorization"], "not_verified")
            self.assertEqual(report["evaluation"]["accepted_record_count"], 0)
            serialized = json.dumps(report)
            self.assertNotIn("MN22-37709", serialized)
            self.assertNotIn("ABC123", serialized)
            self.assertNotIn("10 Main Street", serialized)
            self.assertNotIn("redacted treatment", serialized)
            self.assertEqual(report["privacy_scan"]["candidate_counts"]["member_id_label"], 1)
            self.assertEqual(report["privacy_scan"]["candidate_counts"]["date_of_birth_label"], 1)
            self.assertEqual(report["privacy_scan"]["candidate_counts"]["physical_address_shape"], 1)
            self.assertEqual(report["inspection"]["outcome_nonempty"], 1)
            self.assertEqual(report["inspection"]["outcome_distinct_count"], 1)


if __name__ == "__main__":
    unittest.main()
