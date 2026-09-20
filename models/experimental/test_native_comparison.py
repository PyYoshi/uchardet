# SPDX-License-Identifier: MIT
import copy
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import native_comparison
import test_filtered_evaluation as fixture


class NativeComparisonTests(unittest.TestCase):
    setUp = fixture.FilteredEvaluationTests.setUp
    baseline = fixture.FilteredEvaluationTests.baseline
    validation_manifest = fixture.FilteredEvaluationTests.validation_manifest

    def test_split_and_training_leakage_checked_before_read(self):
        manifest, root = self.validation_manifest()
        for kind in ("independent", "sha256", "origin"):
            value = copy.deepcopy(manifest)
            if kind == "independent":
                value["sources"][0]["split"] = kind
            else:
                value["sources"][0][kind] = self.artifact["documents"][0]["source"][kind]
            with patch.object(native_comparison, "select") as select:
                with self.assertRaises(ValueError):
                    native_comparison.select_records(
                        self.baseline(), self.artifact, value, root, "validation"
                    )
                select.assert_not_called()
        with self.assertRaisesRegex(ValueError, "sealed"):
            native_comparison.select_records(
                self.baseline(), self.artifact, manifest, root, "independent"
            )

    def test_summary_preserves_nonprobability_values(self):
        observations = [
            dict(observation=dict(snapshot=dict(state=state, confidence_bits=bits)))
            for state, bits in ((0, "bf800000"), (1, "40000000"), (2, "7f800000"))
        ]
        result = native_comparison.summarize(observations)
        self.assertEqual(result["states"], dict(detecting=1, found=1, rejected=1))
        self.assertEqual(result["confidence_min"], -1)
        self.assertEqual(result["confidence_max"], 2)
        self.assertEqual(result["nonfinite_confidences"], 1)
        self.assertEqual(result["below_zero"], 1)
        self.assertEqual(result["above_one"], 1)
        self.assertIsNone(native_comparison.summarize([])["confidence_min"])

    def test_invalid_state_rejected(self):
        for state in (-1, 3, True):
            with self.assertRaises(ValueError):
                native_comparison.summarize([dict(observation=dict(snapshot=dict(state=state)))])

    @unittest.skipUnless(os.environ.get("UCHARDET_STATIC_LIBRARY"), "native library not configured")
    def test_real_reference_and_generated_comparison(self):
        library = Path(os.environ["UCHARDET_STATIC_LIBRARY"])
        manifest, root = self.validation_manifest()
        # The model artifact's diagnostic binary identity is independent of the probe library.
        # This synthetic artifact was already validated in setUp; no detector data is learned here.
        report = native_comparison.compare(
            self.baseline(),
            self.artifact,
            manifest,
            root,
            "validation",
            library,
            os.environ.get("UCHARDET_PROBE_CXX", "c++"),
        )
        self.assertEqual(report["legacy_training_overlap"], "UNKNOWN")
        legacy = report["profiles"]["legacy"]
        self.assertEqual(legacy["provenance"]["reference_symbol"], "Windows_1252FrenchModel")
        self.assertNotIn("contract_hash", legacy["provenance"])
        self.assertIsNone(legacy["training_artifact_hash"])
        for name, result in report["profiles"].items():
            self.assertEqual(result["summary"]["documents"], 1)
            observed = result["documents"][0]["observation"]
            self.assertEqual(observed["model_language"], "fr")
            self.assertEqual(
                observed["model_encoding"].lower(), "windows-1252" if name == "legacy" else "cp1252"
            )
            self.assertEqual(observed["raw_bytes"], 16)
            self.assertEqual(observed["filtered_bytes"], 8)
        self.assertEqual(
            report["profiles"]["filtered"]["documents"][0]["observation"]["snapshot"][
                "total_sequences"
            ],
            5,
        )


if __name__ == "__main__":
    unittest.main()
