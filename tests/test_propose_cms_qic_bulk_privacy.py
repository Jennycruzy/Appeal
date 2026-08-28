from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from propose_cms_qic_bulk_privacy import recommendation  # noqa: E402


class CmsQicBulkPrivacyProposalTests(unittest.TestCase):
    def test_contact_shapes_remain_pending_context_review(self) -> None:
        decision, basis = recommendation("Contact reviewer@example.org", ["email_shape"])

        self.assertEqual(decision, "l")
        self.assertEqual(basis, "email_shape_requires_context_review")

    def test_member_value_shape_is_blocked(self) -> None:
        decision, basis = recommendation("member ID: ABC12345", ["member_id_label"])

        self.assertEqual(decision, "b")
        self.assertEqual(basis, "member_id_with_value_shape_requires_block")

    def test_member_label_without_numeric_value_is_false_positive(self) -> None:
        decision, basis = recommendation("The member ID is required for coverage.", ["member_id_label"])

        self.assertEqual(decision, "f")
        self.assertEqual(basis, "member_id_label_without_value_shape")

    def test_measurement_address_match_is_false_positive(self) -> None:
        value = "The requested quantity was 30 per 30 days and the rule was upheld."

        decision, basis = recommendation(value, ["physical_address_shape"])

        self.assertEqual(decision, "f")
        self.assertEqual(basis, "technical_pattern_not_confirmed_as_identifier")

    def test_ambiguous_address_shape_stays_for_context_review(self) -> None:
        decision, basis = recommendation("The letter refers to 10 Main Street.", ["physical_address_shape"])

        self.assertEqual(decision, "l")
        self.assertEqual(basis, "physical_address_shape_requires_context_review")


if __name__ == "__main__":
    unittest.main()
