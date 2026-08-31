from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from score_cms_qic_outcomes import score as score_outcomes  # noqa: E402
from score_cms_qic_legal_ground import score as score_legal_ground  # noqa: E402


def reference(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def benchmark_payload() -> tuple[list[dict[str, object]], dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, outcome in enumerate(("Favorable", "Unfavorable")):
        case = reference(f"case-{index}")
        rationale = f"The operative holding for case {index} is stated here."
        policy = f"The applicable policy criterion for case {index} is stated here."
        rows.append(
            {
                "schema_version": "1.0",
                "case_ref": case,
                "source": {"source_id": "cms_qic_decision_summaries"},
                "split": "locked_test",
                "model_input": {
                    "part": "Part D-Drug",
                    "appeal_type": "Exception",
                    "condition": "Condition",
                    "requested_item_or_drug": f"Drug {index}",
                    "decision_rationale": rationale,
                    "policy_context": policy,
                },
                "hidden_labels": {
                    "regulator_outcome": outcome,
                },
            }
        )
    return rows, {"locked_test_size": 2, "split_counts": {"locked_test": 2}}


class CmsQicTrackScoringTests(unittest.TestCase):
    def prepare_benchmark(self, folder: Path) -> tuple[Path, Path, list[dict[str, object]]]:
        rows, sampling = benchmark_payload()
        benchmark = folder / "benchmark.jsonl"
        benchmark.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
        digest = hashlib.sha256()
        for row in sorted(rows, key=lambda item: str(item["case_ref"])):
            digest.update(str(row["case_ref"]).encode("ascii"))
            digest.update(b"\n")
        sampling["sample_identity_sha256"] = digest.hexdigest()
        manifest = folder / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "status": "cms_qic_legal_ground_benchmark_sample_ready",
                    "artifact": {"sha256": hashlib.sha256(benchmark.read_bytes()).hexdigest()},
                    "sampling": sampling,
                }
            ),
            encoding="utf-8",
        )
        return benchmark, manifest, rows

    def test_official_outcome_score_counts_abstention_separately(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            folder = Path(directory)
            benchmark, manifest, rows = self.prepare_benchmark(folder)
            predictions = folder / "outcomes.jsonl"
            predictions.write_text(
                json.dumps({"case_ref": rows[0]["case_ref"], "regulator_outcome": "favorable"})
                + "\n"
                + json.dumps({"case_ref": rows[1]["case_ref"], "abstained": True})
                + "\n",
                encoding="utf-8",
            )
            report = score_outcomes(benchmark, manifest, predictions, folder / "report.json")

        self.assertEqual(report["status"], "cms_qic_official_outcome_score_ready")
        self.assertEqual(report["metrics"]["selective_accuracy"]["numerator"], 1)
        self.assertEqual(report["metrics"]["selective_accuracy"]["denominator"], 1)
        self.assertEqual(report["metrics"]["coverage"]["value"], 0.5)
        self.assertEqual(report["metrics"]["accuracy_including_abstentions_as_incorrect"]["value"], 0.5)
        self.assertTrue(report["claim_boundary"]["official_CMS_outcome_scoring"])
        self.assertFalse(report["claim_boundary"]["inferred_legal_ground_scoring"])

    def test_official_outcome_score_rejects_narrative_prediction_fields(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            folder = Path(directory)
            benchmark, manifest, rows = self.prepare_benchmark(folder)
            predictions = folder / "outcomes.jsonl"
            rows_payload = [
                {
                    "case_ref": row["case_ref"],
                    "regulator_outcome": "favorable",
                    "model_input": row["model_input"],
                }
                for row in rows
            ]
            predictions.write_text("\n".join(json.dumps(row) for row in rows_payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "forbidden field"):
                score_outcomes(benchmark, manifest, predictions, folder / "report.json")

    def test_legal_ground_score_is_a_distinct_human_gold_track(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            folder = Path(directory)
            benchmark, manifest, rows = self.prepare_benchmark(folder)
            taxonomy = folder / "taxonomy.json"
            taxonomy.write_text(json.dumps({"taxonomy_id": "cms_part_d_legal_ground_v2"}), encoding="utf-8")
            rationale = rows[0]["model_input"]["decision_rationale"]
            policy = rows[0]["model_input"]["policy_context"]
            rationale_hash = hashlib.sha256(rationale.encode("utf-8")).hexdigest()
            policy_hash = hashlib.sha256(policy.encode("utf-8")).hexdigest()
            gold_rows: list[dict[str, object]] = []
            prediction_rows: list[dict[str, object]] = []
            for index, row in enumerate(rows):
                rationale_value = row["model_input"]["decision_rationale"]
                policy_value = row["model_input"]["policy_context"]
                rationale_hash = hashlib.sha256(rationale_value.encode("utf-8")).hexdigest()
                policy_hash = hashlib.sha256(policy_value.encode("utf-8")).hexdigest()
                gold_rows.append(
                    {
                        "case_ref": row["case_ref"],
                        "taxonomy_version": "cms_part_d_legal_ground_v2",
                        "resolution": "consensus",
                        "primary_category": "prior_authorization",
                        "secondary_categories": [],
                        "disposition": "annotated",
                        "route": "utilization_management_exception",
                        "rationale_spans": [
                            {
                                "source_field": "decision_rationale",
                                "start": 0,
                                "end": len(rationale_value),
                                "source_sha256": rationale_hash,
                                "span_role": "operative_holding",
                            }
                        ],
                        "policy_spans": [],
                        "confidence": 4,
                    }
                )
                prediction_rows.append(
                    {
                        key: value
                        for key, value in gold_rows[-1].items()
                        if key not in {"resolution", "confidence"}
                    }
                )
            gold = folder / "gold.jsonl"
            gold.write_text("\n".join(json.dumps(row) for row in gold_rows) + "\n", encoding="utf-8")
            predictions = folder / "legal.jsonl"
            predictions.write_text("\n".join(json.dumps(row) for row in prediction_rows) + "\n", encoding="utf-8")
            report = score_legal_ground(benchmark, manifest, gold, predictions, taxonomy, folder / "report.json")

        self.assertEqual(report["status"], "cms_qic_legal_ground_score_ready")
        self.assertEqual(report["metrics"]["primary_category_accuracy"]["value"], 1.0)
        self.assertEqual(report["metrics"]["issue_set"]["micro_f1"], 1.0)
        self.assertTrue(report["claim_boundary"]["inferred_legal_ground_scoring"])
        self.assertFalse(report["claim_boundary"]["official_CMS_outcome_scoring"])


if __name__ == "__main__":
    unittest.main()
