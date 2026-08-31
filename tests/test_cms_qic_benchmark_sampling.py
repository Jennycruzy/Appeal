from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from accept_cms_qic_bulk import content_identity, occurrence_identity, selection_fingerprint  # noqa: E402
from audit_cms_qic_benchmark import audit  # noqa: E402
from inspect_cms_qic_bulk import row_fingerprint, sha256_file  # noqa: E402
from sample_cms_qic_benchmark import allocate, build  # noqa: E402


HEADERS = [
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


def rows() -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    for index in range(12):
        values.append(
            {
                "Part": "Part D-Drug",
                "Decision_Date": f"01/{index + 1:02d}/202{index % 2}",
                "Decision_Date_Sortable": f"202{index % 2}01{index + 1:02d}",
                "Decision": "Favorable" if index % 3 == 0 else "Unfavorable",
                "Appeal_Type": "Exception" if index % 2 == 0 else "Prescription Drug",
                "Condition": f"Condition {index}",
                "Drug": f"Drug {index}",
                "Decision_Rationale": f"Private local rationale {index}",
                "Coverage_Rules": f"Private local coverage rule {index}",
            }
        )
    return values


def prepare(folder: Path) -> tuple[Path, Path]:
    csv_path = folder / "cms.csv"
    source_rows = rows()
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(source_rows)
    file_hash = sha256_file(csv_path)
    accepted: list[str] = []
    excluded: list[str] = []
    excluded_record: dict[str, object] | None = None
    for row_number, row in enumerate(source_rows, start=1):
        row_hash = row_fingerprint(row)
        occurrence = occurrence_identity(content_identity(file_hash, row_hash), row_number)
        if row_number == 4:
            excluded.append(occurrence)
            excluded_record = {"csv_data_row": row_number, "row_sha256": row_hash}
        else:
            accepted.append(occurrence)
    assert excluded_record is not None
    manifest = {
        "source": {"sha256": file_hash},
        "selection": {
            "excluded_rows": [excluded_record],
            "excluded_row_count": 1,
            "accepted_occurrence_selection_fingerprint_sha256": selection_fingerprint(accepted),
            "excluded_occurrence_selection_fingerprint_sha256": selection_fingerprint(excluded),
        },
        "acceptance": {
            "accepted_for_local_evaluation": True,
            "accepted_for_repository": False,
            "accepted_record_count": 11,
        },
    }
    manifest_path = folder / "acceptance.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return csv_path, manifest_path


class CmsQicBenchmarkSamplingTests(unittest.TestCase):
    def test_allocation_is_exact_and_preserves_each_feasible_stratum(self) -> None:
        result = allocate({"large": 20, "small": 2, "rare": 1}, 10)
        self.assertEqual(sum(result.values()), 10)
        self.assertEqual(set(result), {"large", "small", "rare"})
        self.assertGreaterEqual(result["rare"], 1)
        self.assertLessEqual(result["small"], 2)

    def test_sampler_enforces_exclusion_hides_outcome_and_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as first_directory, tempfile.TemporaryDirectory(dir=ROOT.parent) as second_directory:
            first = Path(first_directory)
            second = Path(second_directory)
            first_csv, first_manifest = prepare(first)
            second_csv, second_manifest = prepare(second)
            first_output = first / "sample.jsonl"
            second_output = second / "sample.jsonl"
            first_report = build(first_csv, first_manifest, first_output, sample_size=8, locked_size=3, seed="fixed-seed")
            second_report = build(second_csv, second_manifest, second_output, sample_size=8, locked_size=3, seed="fixed-seed")

            self.assertEqual(first_output.read_bytes(), second_output.read_bytes())
            self.assertEqual(first_report["sampling"], second_report["sampling"])
            records = [json.loads(line) for line in first_output.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(len(records), 8)
        self.assertEqual({record["split"] for record in records}, {"development", "locked_test"})
        self.assertEqual(sum(record["split"] == "locked_test" for record in records), 3)
        for record in records:
            self.assertNotIn("regulator_outcome", record["model_input"])
            self.assertIn("regulator_outcome", record["hidden_labels"])
        self.assertFalse(first_report["claim_boundary"]["complete_denial_package"])

    def test_sampler_fails_on_excluded_row_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            folder = Path(directory)
            csv_path, manifest_path = prepare(folder)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["selection"]["excluded_rows"][0]["row_sha256"] = "f" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "excluded row hash mismatch"):
                build(csv_path, manifest_path, folder / "sample.jsonl", sample_size=8, locked_size=3, seed="fixed-seed")

    def test_audit_separates_schema_extraction_from_quality_claims(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            folder = Path(directory)
            csv_path, acceptance_path = prepare(folder)
            output = folder / "sample.jsonl"
            sample_manifest = build(csv_path, acceptance_path, output, sample_size=8, locked_size=3, seed="fixed-seed")
            sample_manifest_path = folder / "sample-manifest.json"
            sample_manifest_path.write_text(json.dumps(sample_manifest), encoding="utf-8")
            report = audit(output, sample_manifest_path)

        self.assertTrue(report["claim_boundary"]["real_world_regulator_summary_benchmark"])
        self.assertFalse(report["claim_boundary"]["clinical_efficacy"])
        self.assertFalse(report["baselines"]["explicit_appeal_type_passthrough"]["quality_claim_allowed"])
        self.assertEqual(report["source"]["locked_test_count"], 3)


if __name__ == "__main__":
    unittest.main()
