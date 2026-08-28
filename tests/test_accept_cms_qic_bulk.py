from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from accept_cms_qic_bulk import build_manifest  # noqa: E402
from inspect_cms_qic_bulk import inspect  # noqa: E402


class CmsQicBulkAcceptanceTests(unittest.TestCase):
    def test_user_policy_accepts_f_and_excludes_non_f_without_raw_values(self) -> None:
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
        rows = [
            {
                field: "part_d" if field == "Part" else (
                    "The dose was 10 Main Street." if field == "Decision_Rationale" else "value"
                )
                for field in headers
            },
            {
                field: "part_d" if field == "Part" else (
                    "Member ID: ABC12345" if field == "Decision_Rationale" else "value"
                )
                for field in headers
            },
        ]

        with TemporaryDirectory() as directory:
            directory_path = Path(directory)
            csv_path = directory_path / "part-d.csv"
            report_path = directory_path / "inspection.json"
            proposal_path = directory_path / "proposal.json"
            with csv_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)
            report = inspect(
                csv_path,
                part="part_d",
                source_url="https://downloads.cms.gov/qic/partd.csv",
                source_etag='"etag"',
                expected_record_count=2,
            )
            report_path.write_text(json.dumps(report), encoding="utf-8")
            decisions = {
                locator["value_sha256"]: ("f" if locator["csv_data_row"] == 1 else "b")
                for locator in report["candidate_locators"]
            }
            proposal_path.write_text(
                json.dumps(
                    {
                        "status": "agent_proposed_pending_user_verification",
                        "source": {
                            "source_id": report["source_id"],
                            "sha256": report["artifact"]["sha256"],
                        },
                        "privacy_review": {
                            "candidate_record_count": len(decisions),
                            "decision_count": len(decisions),
                            "unresolved_count": 0,
                            "raw_values_in_decision_file": False,
                            "decisions": [
                                {"value_sha256": value_hash, "decision": decision}
                                for value_hash, decision in decisions.items()
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )

            manifest = build_manifest(
                csv_path,
                report_path,
                proposal_path,
                reviewer="workspace-owner-explicit-direction",
            )

        self.assertEqual(manifest["acceptance"]["accepted_record_count"], 1)
        self.assertEqual(manifest["acceptance"]["excluded_record_count"], 1)
        self.assertEqual(manifest["privacy_review"]["decision_counts"], {"b": 1, "f": 1})
        self.assertEqual(manifest["selection"]["excluded_row_count"], 1)
        self.assertEqual(manifest["identity"]["source_record_number"], "missing_in_bulk_export_not_resolved_or_invented")
        serialized = json.dumps(manifest)
        self.assertNotIn("The dose was 10 Main Street.", serialized)
        self.assertNotIn("Member ID: ABC12345", serialized)


if __name__ == "__main__":
    unittest.main()
