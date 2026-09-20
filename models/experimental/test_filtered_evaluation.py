# SPDX-License-Identifier: MIT
import copy
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import filtered_evaluation as evaluation
import filtered_training
import sequence_evaluation as coverage
import sequence_training
import test_filtered_training as fixture
from framework import generate
from model import canonical, digest
from sequence_contract import content_hash


class FilteredEvaluationTests(unittest.TestCase):
    setUp = fixture.FilteredTrainingTests.setUp

    def validation_manifest(self):
        text = "outside thé café".encode()
        (self.root / "heldout.txt").write_bytes(text)
        source = dict(
            id="heldout",
            path="heldout.txt",
            language="fr",
            license="MIT",
            license_reference="corpus/LICENSES/MIT.txt",
            revision="synthetic-v1",
            origin="synthetic:heldout",
            kind="synthetic",
            sha256=digest(text),
            split="validation",
        )
        root = self.root / "validation"
        manifest = generate(
            dict(
                sources=[source],
                encodings=["cp1252"],
                byte_limits=[None, 3],
                formats=["text", "html-clean"],
            ),
            self.root,
            root,
        )
        return manifest, root

    def baseline(self):
        return sequence_training.train(self.manifest, self.root / "corpus", "fr")

    def test_statistical_counts_equal_direct_byte_counts(self):
        contract = self.artifact["contract"]
        known = evaluation.known_letters(self.artifact)
        for data in (b"", b"abc", b"caf\xe9 ", b" 12 ", b"th\xe9 caf\xe9", b"\x00\nAZaz"):
            with self.subTest(data=data):
                self.assertEqual(
                    evaluation.counts(sequence_training.count_document(data), contract, known),
                    coverage.counts(data, contract, known),
                )

    def test_same_observation_used_for_both_models_and_repeatable(self):
        manifest, root = self.validation_manifest()
        observed = fixture.observation(b"outside th\xe9 caf\xe9", b"th\xe9 caf\xe9")
        with patch.object(filtered_training, "observe", return_value=observed) as observe:
            report = evaluation.evaluate(
                self.baseline(), self.artifact, manifest, root, "validation", self.binary
            )
            observe.assert_called_once()
            repeated = evaluation.evaluate(
                self.baseline(), self.artifact, manifest, root, "validation", self.binary
            )
        self.assertEqual(canonical(report), canonical(repeated))
        self.assertEqual(report["content_hash"], content_hash(report))
        self.assertEqual(len(report["observations"]), 1)
        for profile in report["profiles"].values():
            self.assertEqual(profile["source_count"], 1)
            self.assertEqual(profile["aggregate_counts"]["bytes"], 8)
            populated = [s for s in profile["raw_size_strata"] if s["source_count"]]
            self.assertEqual(populated[0]["minimum_raw_bytes_inclusive"], 16)
        # Unknown t/h are not promoted into the frozen filtered training alphabet.
        self.assertEqual(report["profiles"]["filtered"]["aggregate_counts"]["unknown_letters"], 2)

    def test_leakage_and_independent_rejected_before_read(self):
        manifest, root = self.validation_manifest()
        for field in ("sha256", "origin", "independent"):
            altered = copy.deepcopy(manifest)
            if field == "independent":
                altered["sources"][0]["split"] = "independent"
            else:
                altered["sources"][0][field] = self.artifact["documents"][0]["source"][field]
            with patch.object(evaluation, "select") as select:
                with self.assertRaises(ValueError):
                    evaluation.evaluate(
                        self.baseline(), self.artifact, altered, root, "validation", self.binary
                    )
                select.assert_not_called()
        with self.assertRaisesRegex(ValueError, "sealed"):
            evaluation.evaluate(
                self.baseline(), self.artifact, manifest, root, "independent", self.binary
            )

    def test_other_binary_rejected_before_observation(self):
        manifest, root = self.validation_manifest()
        self.binary.write_bytes(b"different build")
        with patch.object(filtered_training, "observe") as observe:
            with self.assertRaisesRegex(ValueError, "training native binary"):
                evaluation.evaluate(
                    self.baseline(), self.artifact, manifest, root, "validation", self.binary
                )
            observe.assert_not_called()

    def test_wrong_training_source_rejected(self):
        baseline = copy.deepcopy(self.baseline())
        baseline["documents"][0]["source"]["origin"] = "synthetic:different-training"
        baseline["contract"]["provenance"]["sources"][0]["origin"] = "synthetic:different-training"
        baseline["contract"]["content_hash"] = content_hash(baseline["contract"])
        baseline["content_hash"] = content_hash(baseline)
        sequence_training.validate(baseline)
        manifest, root = self.validation_manifest()
        with self.assertRaisesRegex(ValueError, "same training sources"):
            evaluation.evaluate(baseline, self.artifact, manifest, root, "validation", self.binary)

    def test_zero_evidence_rates_undefined(self):
        manifest, root = self.validation_manifest()
        with patch.object(
            filtered_training,
            "observe",
            return_value=fixture.observation(b"outside th\xe9 caf\xe9", b""),
        ):
            report = evaluation.evaluate(
                self.baseline(), self.artifact, manifest, root, "validation", self.binary
            )
        for profile in report["profiles"].values():
            self.assertTrue(all(rate is None for rate in profile["aggregate_rates"].values()))
            self.assertEqual(
                profile["macro_rates"]["matrix_pair_coverage"]["undefined_documents"], 1
            )

    @unittest.skipUnless(os.environ.get("UCHARDET_FILTER_PROFILE"), "native tool not configured")
    def test_actual_native_evaluation(self):
        binary = Path(os.environ["UCHARDET_FILTER_PROFILE"])
        training = filtered_training.train(self.manifest, self.root / "corpus", "fr", binary)
        manifest, root = self.validation_manifest()
        report = evaluation.evaluate(
            self.baseline(), training, manifest, root, "validation", binary
        )
        self.assertEqual(
            report["observations"][0]["observation"],
            fixture.observation(b"outside th\xe9 caf\xe9", b"th\xe9 caf\xe9"),
        )
        self.assertEqual(report["profiles"]["filtered"]["aggregate_counts"]["matrix_pairs"], 3)


if __name__ == "__main__":
    unittest.main()
