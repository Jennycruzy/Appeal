import unittest

from scripts.run_adk_case import EXPECTED_AGENTS, _synthetic_case_prompt, _synthetic_scanned_pdf


class AdkCaseFixtureTests(unittest.TestCase):
    def test_synthetic_fixture_is_an_image_only_pdf(self) -> None:
        pdf = _synthetic_scanned_pdf()
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertTrue(pdf.endswith(b"%%EOF\n"))
        self.assertIn(b"/Subtype /Image", pdf)
        self.assertIn(b"/Filter /FlateDecode", pdf)
        self.assertIn(b"/Im0 Do", pdf)

    def test_prompt_requires_the_pdf_for_denial_fields(self) -> None:
        prompt = _synthetic_case_prompt()
        self.assertIn("attached image-only PDF is the denial source", prompt)
        self.assertNotIn("requested service: advanced imaging", prompt.lower())
        self.assertEqual(
            EXPECTED_AGENTS,
            (
                "intake",
                "denial_parser",
                "policy_analyst",
                "evidence_miner",
                "argument_builder",
                "deadline_sentinel",
                "escalation_strategist",
            ),
        )


if __name__ == "__main__":
    unittest.main()
