from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RealDenialPathTests(unittest.TestCase):
    def test_washington_source_is_discovery_only_and_fail_closed(self) -> None:
        manifest = json.loads(
            (ROOT / "evidence" / "wa-oic-iro-search.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["status"], "discovery_candidate_not_acquired")
        self.assertEqual(manifest["source"]["case_rows_acquired"], 0)
        self.assertFalse(manifest["source"]["raw_rows_written"])
        self.assertFalse(manifest["acceptance"]["accepted_for_local_evaluation"])
        self.assertEqual(manifest["acceptance"]["accepted_record_count"], 0)
        self.assertNotEqual(manifest["gates"]["schema"]["status"], "pass")
        self.assertNotEqual(manifest["gates"]["reuse"]["status"], "pass")

    def test_full_case_manifest_stays_blocked_until_authorized_package(self) -> None:
        manifest = json.loads(
            (ROOT / "evidence" / "full-appeal-case-corpus-acceptance.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(manifest["status"], "acquisition_required")
        self.assertFalse(manifest["acceptance"]["accepted_for_local_evaluation"])
        self.assertFalse(manifest["evaluation"]["full_appeal_evaluation_allowed"])


if __name__ == "__main__":
    unittest.main()
