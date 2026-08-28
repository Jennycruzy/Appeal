from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from inspect_cms_qic_bulk import inspect  # noqa: E402
from review_cms_qic_bulk_privacy import (  # noqa: E402
    candidate_groups,
    load_candidate_values,
    write_decisions,
)


class CmsQicBulkPrivacyReviewTests(unittest.TestCase):
    def test_review_resolves_values_but_persists_only_hashes_and_decisions(self) -> None:
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
        private_value = "member ID 24680 at 10 Main Street"
        row = {field: "value" for field in headers}
        row["Decision_Rationale"] = private_value

        with TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "part-d.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=headers)
                writer.writeheader()
                writer.writerow(row)
            report = inspect(
                csv_path,
                part="part_d",
                source_url="https://downloads.cms.gov/qic/partd.csv",
                source_etag=None,
                expected_record_count=1,
            )
            candidates = candidate_groups(report)
            values = load_candidate_values(csv_path, candidates)
            output = root / "decisions.json"
            write_decisions(
                output,
                source={"file_name": csv_path.name, "sha256": report["artifact"]["sha256"]},
                reviewer="authorized-reviewer",
                candidates=candidates,
                decisions={str(candidates[0]["value_sha256"]): "confirmed_identifier_block"},
                status="complete",
            )
            saved = output.read_text(encoding="utf-8")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(values[str(candidates[0]["value_sha256"])], private_value)
        self.assertNotIn(private_value, saved)
        self.assertIn("confirmed_identifier_block", saved)
        self.assertIn("raw_values_in_decision_file", saved)


if __name__ == "__main__":
    unittest.main()
