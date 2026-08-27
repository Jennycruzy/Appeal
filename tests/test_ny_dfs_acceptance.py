from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_ny_dfs_acceptance import validate_manifest  # noqa: E402


class NyDfsAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads((ROOT / "evidence" / "ny-dfs-acceptance.json").read_text())
        self.acquisition = json.loads((ROOT / "evidence" / "ny-dfs-export-acquisition.json").read_text())

    def test_template_is_structurally_valid_but_blocked(self) -> None:
        errors, ready = validate_manifest(self.manifest, self.acquisition)
        self.assertEqual(errors, [])
        self.assertFalse(ready)

    def test_inferred_mapping_cannot_unlock_appeal_type(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        mapping = manifest["gates"]["schema_mapping"]
        mapping["status"] = "verified"
        mapping["mapping_decision"] = "inferred_from_counts"
        mapping["verified_equivalent"] = True
        mapping["evidence_refs"] = ["unverified-comparison"]
        manifest["field_policy"]["appeal_type"]["status"] = "verified_mapping"
        manifest["field_policy"]["appeal_type"]["source_column"] = "Denial Reason"
        errors, ready = validate_manifest(manifest, self.acquisition)
        self.assertFalse(ready)
        self.assertTrue(any("appeal_type must stay nullable and unverified" in error for error in errors))

    def test_raw_case_records_are_rejected_from_metadata_manifest(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["case_records"] = []
        errors, ready = validate_manifest(manifest, self.acquisition)
        self.assertFalse(ready)
        self.assertIn("manifest.case_records is not allowed in metadata-only manifest", errors)
