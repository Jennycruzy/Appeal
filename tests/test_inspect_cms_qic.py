from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from inspect_cms_qic import (  # noqa: E402
    PART_C_FIELDS,
    PART_C_TITLE,
    catalog_metadata,
    public_query_template,
    summarize_query,
)
from fetch_cms_qic_summary import normalize_row  # noqa: E402
import fetch_cms_qic_summary as cms_fetcher  # noqa: E402


class CmsQicInspectorTests(unittest.TestCase):
    def test_committed_manifest_is_real_summary_metadata_not_a_case_dump(self) -> None:
        manifest = json.loads(
            (ROOT / "evidence" / "cms-qic-decision-search.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(manifest["status"], "accepted_for_regulator_summary_benchmark")
        self.assertEqual(manifest["scope"]["total_records_reported"], 1142429)
        self.assertTrue(manifest["acceptance"]["accepted_for_local_summary_evaluation"])
        self.assertFalse(manifest["acceptance"]["accepted_for_full_appeal_evaluation"])
        self.assertFalse(manifest["source"]["raw_rows_written"])
        self.assertFalse(manifest["acceptance"]["narrative_rows_committed"])

    def test_catalog_metadata_resolves_the_two_official_datasets(self) -> None:
        catalog = [
            {
                "title": PART_C_TITLE,
                "identifier": "part-c-id",
                "description": "summaries",
                "accessLevel": "public",
                "modified": "2026-08-26 14:20:52",
                "license": "https://www.usa.gov/publicdomain/label/1.0/",
                "publisher": {"data": {"name": "qic.cms.gov"}},
                "distribution": [
                    {
                        "identifier": "part-c-distribution",
                        "data": {
                            "format": "csv",
                            "mediaType": "text/csv",
                            "downloadURL": "https://downloads.cms.gov/partc.csv",
                        },
                    }
                ],
            },
            {
                "title": "Part D decision data",
                "identifier": "part-d-id",
                "description": "summaries",
                "accessLevel": "public",
                "license": "https://www.usa.gov/publicdomain/label/1.0/",
            },
        ]

        metadata = catalog_metadata(catalog)

        self.assertEqual(metadata[PART_C_TITLE]["identifier"], "part-c-id")
        self.assertEqual(metadata[PART_C_TITLE]["distribution"]["format"], "csv")
        self.assertEqual(sorted(metadata), ["Part C decision data", "Part D decision data"])

    def test_summary_records_schema_and_privacy_without_emitting_values(self) -> None:
        private_value = "member ID 12345"
        row = {
            field: "value" for field in PART_C_FIELDS
        }
        row["decision_rationale"] = private_value
        payload = {"count": 901471, "results": [row], "schema": {}}

        report = summarize_query(payload, expected_fields=PART_C_FIELDS, sample_limit=3)
        serialized = json.dumps(report)

        self.assertEqual(report["reported_record_count"], 901471)
        self.assertEqual(report["sample_rows_returned"], 1)
        self.assertEqual(report["missing_expected_fields"], [])
        self.assertEqual(report["privacy_scan"]["candidate_counts"]["member_id_label"], 1)
        self.assertNotIn(private_value, serialized)
        self.assertNotIn("decision rationale", serialized)

    def test_query_template_does_not_record_the_public_api_key(self) -> None:
        template = public_query_template("part-c-id")

        self.assertIn("{offset}", template)
        self.assertIn("{limit}", template)
        self.assertNotIn("ACA", template)

    def test_missing_expected_field_is_reported_fail_closed(self) -> None:
        payload = {
            "count": 1,
            "results": [{"record_number": "1", "decision": "upheld"}],
            "schema": {},
        }

        report = summarize_query(payload, expected_fields=PART_C_FIELDS, sample_limit=3)

        self.assertIn("appeal_type", report["missing_expected_fields"])
        self.assertIn("decision_rationale", report["missing_expected_fields"])

    def test_normalizer_keeps_source_summary_fields_separate_from_denial_reason(self) -> None:
        row = {
            "record_number": "17",
            "part": "Part D-Drug",
            "decision_date": "2026-01-02",
            "decision_date_sortable": "20260102",
            "decision": "upheld",
            "appeal_type": "exception",
            "_condition": "condition summary",
            "drug": "drug summary",
            "decision_rationale": "QIC rationale summary",
            "coverage_rules": "coverage rules summary",
        }

        normalized = normalize_row("part_d", row)

        self.assertEqual(normalized["regulator_outcome"], "upheld")
        self.assertEqual(normalized["appeal_type"], "exception")
        self.assertEqual(normalized["decision_rationale"], "QIC rationale summary")
        self.assertIsNone(normalized["denial_reason"])
        self.assertIsNone(normalized["clinical_evidence"])
        self.assertIsNone(normalized["prior_authorization"])
        self.assertNotEqual(normalized["case_id"], "17")

    def test_bounded_extraction_writes_only_normalized_rows_and_aggregate_manifest(self) -> None:
        def row(record_number: str) -> dict[str, str]:
            return {
                "record_number": record_number,
                "part": "Part D-Drug",
                "decision_date": "2026-01-02",
                "decision_date_sortable": "20260102",
                "decision": "upheld",
                "appeal_type": "exception",
                "_condition": "condition summary",
                "drug": "drug summary",
                "decision_rationale": "QIC rationale summary",
                "coverage_rules": "coverage rules summary",
            }

        pages = [
            {"count": 2, "results": [row("1")]},
            {"count": 2, "results": [row("2")]},
        ]
        with TemporaryDirectory() as directory:
            output = Path(directory) / "part-d.jsonl"
            manifest_path = Path(directory) / "part-d.manifest.json"
            with patch.object(cms_fetcher, "fetch_json", side_effect=pages):
                manifest = cms_fetcher.extract(
                    part="part_d",
                    output=output,
                    manifest_path=manifest_path,
                    api_key="test-key",
                    page_size=1,
                    max_records=2,
                    timeout=1,
                )

            rows = [json.loads(line) for line in output.read_text().splitlines()]
            serialized_output = output.read_text()
            serialized_manifest = manifest_path.read_text()

        self.assertEqual(len(rows), 2)
        self.assertEqual(manifest["evaluation"]["records_written"], 2)
        self.assertNotIn('"record_number"', serialized_output)
        self.assertNotIn("QIC rationale summary", serialized_manifest)
        self.assertFalse(manifest["privacy_scan"]["candidate_counts"])


if __name__ == "__main__":
    unittest.main()
