from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_cms_qic_summary_evaluation import run_preflight  # noqa: E402


class CmsQicSummaryEvaluationTests(unittest.TestCase):
    def record(self, case_number: str = "case-1") -> dict[str, object]:
        case_id = hashlib.sha256(case_number.encode("utf-8")).hexdigest()
        return {
            "case_id": case_id,
            "source_id": "cms_qic_decision_summaries",
            "source_dataset": "part_d",
            "source_record_ref_sha256": "a" * 64,
            "source_row_sha256": "b" * 64,
            "regulator_outcome": "upheld",
            "appeal_type": "exception",
            "condition": "condition summary",
            "requested_item_or_drug": "drug summary",
            "decision_rationale": "QIC rationale summary",
            "policy_context": "coverage rules summary",
            "denial_reason": None,
            "clinical_evidence": None,
            "prior_authorization": None,
        }

    def test_summary_rows_abstain_without_becoming_full_appeals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            input_path = folder / "cms-summary.jsonl"
            input_path.write_text(json.dumps(self.record()) + "\n", encoding="utf-8")
            input_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
            manifest_path = folder / "cms-summary.manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "source_id": "cms_qic_decision_summaries",
                        "status": "local_only_extraction_complete",
                        "source": {"part": "part_d"},
                        "artifact": {
                            "sha256": input_hash,
                            "raw_artifact_location": "outside_repository_only",
                            "narrative_fields_local_only": True,
                        },
                        "privacy_scan": {"candidate_counts": {}},
                        "evaluation": {
                            "records_written": 1,
                            "full_appeal_cases_evaluated": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            output_path = folder / "evaluation.json"

            report = run_preflight(
                input_path,
                manifest_path,
                output_path,
                datetime(2026, 8, 28, tzinfo=UTC),
            )
            serialized = json.dumps(report)

        self.assertEqual(report["adapter_preflight"]["cases_seen"], 1)
        self.assertEqual(report["adapter_preflight"]["cases_abstained"], 1)
        self.assertEqual(report["evaluation"]["summary_cases_evaluated"], 0)
        self.assertEqual(report["evaluation"]["full_appeal_cases_evaluated"], 0)
        self.assertEqual(report["regulator_outcomes"]["counts"], {"upheld": 1})
        self.assertEqual(report["appeal_types"]["counts"], {"exception": 1})
        self.assertNotIn("QIC rationale summary", serialized)

    def test_cms_summary_cannot_be_promoted_with_a_denial_reason(self) -> None:
        record = self.record()
        record["denial_reason"] = "invented mapping"
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            input_path = folder / "cms-summary.jsonl"
            input_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            input_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
            manifest_path = folder / "cms-summary.manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "source_id": "cms_qic_decision_summaries",
                        "status": "local_only_extraction_complete",
                        "source": {"part": "part_d"},
                        "artifact": {
                            "sha256": input_hash,
                            "raw_artifact_location": "outside_repository_only",
                            "narrative_fields_local_only": True,
                        },
                        "privacy_scan": {"candidate_counts": {}},
                        "evaluation": {
                            "records_written": 1,
                            "full_appeal_cases_evaluated": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "denial_reason must remain null"):
                run_preflight(
                    input_path,
                    manifest_path,
                    folder / "evaluation.json",
                    datetime(2026, 8, 28, tzinfo=UTC),
                )


if __name__ == "__main__":
    unittest.main()
