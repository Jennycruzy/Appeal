from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_evaluation_fixture import report_document  # noqa: E402


class EvaluationFixtureTests(unittest.TestCase):
    def test_fixture_report_is_reproducible_and_source_scoped(self) -> None:
        fixture = ROOT / "config" / "evaluation_fixture.json"
        first = report_document(fixture)
        second = report_document(fixture)

        self.assertEqual(first, second)
        self.assertEqual(first["case_count"], 2)
        source = first["source"]
        self.assertIsInstance(source, dict)
        assert isinstance(source, dict)
        self.assertFalse(source["complete_denial_package"])
        self.assertFalse(source["clinical_ground_truth"])
        metrics = first["metrics"]
        self.assertIsInstance(metrics, list)
        assert isinstance(metrics, list)
        appeal_type = next(metric for metric in metrics if metric["task"] == "appeal_type")
        self.assertEqual(appeal_type["denominator"], 1)
        self.assertEqual(appeal_type["abstentions"], 1)


if __name__ == "__main__":
    unittest.main()
