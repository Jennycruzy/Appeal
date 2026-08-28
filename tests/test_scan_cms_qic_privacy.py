from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import scan_cms_qic_privacy as scanner  # noqa: E402


class CmsQicPrivacyScannerTests(unittest.TestCase):
    def test_scan_records_only_hashed_privacy_locators(self) -> None:
        row = {
            "record_number": "17",
            "part": "Part D-Drug",
            "decision": "Unfavorable",
            "decision_rationale": "member ID 12345",
        }
        pages = [{"count": 1, "results": [row]}]

        with TemporaryDirectory() as directory:
            output = Path(directory) / "privacy.json"
            with patch.object(scanner, "fetch_json", side_effect=pages):
                report = scanner.scan(
                    part="part_d",
                    output=output,
                    api_key="test-key",
                    page_size=1,
                    timeout=1,
                )
            serialized = output.read_text(encoding="utf-8")

        self.assertEqual(report["source"]["rows_scanned"], 1)
        self.assertEqual(report["status"], "privacy_candidates_require_human_review")
        self.assertEqual(report["privacy_scan"]["candidate_locator_count"], 1)
        self.assertEqual(report["privacy_scan"]["candidate_counts"], {"member_id_label": 1})
        self.assertNotIn("member ID 12345", serialized)
        self.assertNotIn('"record_number"', serialized)
        locator = report["candidate_locators"][0]
        self.assertEqual(locator["field"], "decision_rationale")
        self.assertEqual(locator["value_length"], len("member ID 12345"))
        self.assertNotEqual(locator["value_sha256"], "member ID 12345")

    def test_clean_scan_is_not_marked_for_human_privacy_review(self) -> None:
        pages = [{"count": 1, "results": [{"record_number": "17", "decision": "Unfavorable"}]}]

        with TemporaryDirectory() as directory:
            output = Path(directory) / "privacy.json"
            with patch.object(scanner, "fetch_json", side_effect=pages):
                report = scanner.scan(
                    part="part_d",
                    output=output,
                    api_key="test-key",
                    page_size=1,
                    timeout=1,
                )

        self.assertEqual(report["status"], "privacy_scan_complete_no_candidates")
        self.assertEqual(report["privacy_scan"]["candidate_locator_count"], 0)
        self.assertFalse(report["human_review"]["required_before_full_extraction_acceptance"])
        self.assertNotIn("record_number", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
