# SPDX-License-Identifier: MIT
import copy
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import paired_controls
import test_filtered_evaluation as fixture
from framework import generate
from model import digest


class PairedControlTests(unittest.TestCase):
    setUp = fixture.FilteredEvaluationTests.setUp
    baseline = fixture.FilteredEvaluationTests.baseline

    def validation(self, text="outside thé café", encodings=("cp1252", "utf-8")):
        data = text.encode()
        (self.root / "heldout.txt").write_bytes(data)
        source = dict(
            id="heldout",
            path="heldout.txt",
            language="fr",
            license="MIT",
            license_reference="corpus/LICENSES/MIT.txt",
            revision="synthetic-v1",
            origin="synthetic:paired-heldout",
            kind="synthetic",
            sha256=digest(data),
            split="validation",
        )
        root = self.root / "validation"
        manifest = generate(
            dict(
                sources=[source],
                encodings=list(encodings),
                byte_limits=[None, 3],
                formats=["text", "html-clean"],
            ),
            self.root,
            root,
        )
        return manifest, root

    def test_pairs_are_same_source_same_text_full_documents(self):
        manifest, root = self.validation()
        records, pairs = paired_controls.select_pairs(
            self.baseline(), self.artifact, manifest, root, "validation"
        )
        self.assertEqual(len(records), 2)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(records[0][0], records[1][0])
        self.assertEqual(records[0][2].decode("cp1252"), records[1][2].decode("utf-8"))
        self.assertFalse(pairs[0]["bytes_identical"])
        self.assertEqual([s["encoding"] for _, s, _ in records], ["cp1252", "utf-8"])

    def test_ascii_marked_ambiguous_not_negative(self):
        manifest, root = self.validation("plain ASCII only")
        _, pairs = paired_controls.select_pairs(
            self.baseline(), self.artifact, manifest, root, "validation"
        )
        self.assertTrue(pairs[0]["bytes_identical"])
        summary = paired_controls.separation([], pairs)
        self.assertEqual(summary["byte_identical_pairs"], 1)
        self.assertEqual(summary["finite_distinct_pairs"], 0)

    def test_utf8_validity_does_not_imply_cp1252_decodability(self):
        manifest, root = self.validation("bonjour ” café")
        _, pairs = paired_controls.select_pairs(
            self.baseline(), self.artifact, manifest, root, "validation"
        )
        self.assertFalse(pairs[0]["control_cp1252_decodable"])

    def test_missing_counterpart_is_error(self):
        manifest, root = self.validation(encodings=("cp1252",))
        with self.assertRaisesRegex(ValueError, "exactly one"):
            paired_controls.select_pairs(
                self.baseline(), self.artifact, manifest, root, "validation"
            )

    def test_control_bytes_revalidated(self):
        manifest, root = self.validation()
        control = next(s for s in manifest["samples"] if s["encoding"] == "utf-8")
        (root / control["path"]).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            paired_controls.select_pairs(
                self.baseline(), self.artifact, manifest, root, "validation"
            )

    def test_independent_refused_before_sample_read(self):
        manifest, root = self.validation()
        manifest = copy.deepcopy(manifest)
        manifest["sources"][0]["split"] = "independent"
        with patch.object(paired_controls, "safe_path") as read:
            with self.assertRaisesRegex(ValueError, "sealed"):
                paired_controls.select_pairs(
                    self.baseline(), self.artifact, manifest, root, "validation"
                )
            read.assert_not_called()

    def test_separation_nonfinite_ties_and_direction(self):
        pairs, documents = [], []
        for index, (positive, control) in enumerate(
            (
                ("3f800000", "00000000"),
                ("00000000", "3f800000"),
                ("00000000", "80000000"),
                ("7fc00000", "00000000"),
            )
        ):
            names = [f"{index}-positive", f"{index}-control"]
            pairs.append(
                dict(positive_sample=names[0], control_sample=names[1], bytes_identical=False)
            )
            documents.extend(
                dict(sample_id=name, observation=dict(snapshot=dict(confidence_bits=bits)))
                for name, bits in zip(names, (positive, control))
            )
        self.assertEqual(
            paired_controls.separation(documents, pairs),
            dict(
                total_pairs=4,
                byte_identical_pairs=0,
                finite_distinct_pairs=3,
                nonfinite_distinct_pairs=1,
                positive_higher=1,
                equal=1,
                control_higher=1,
            ),
        )

    @unittest.skipUnless(os.environ.get("UCHARDET_STATIC_LIBRARY"), "native library not configured")
    def test_actual_paired_native_observations(self):
        manifest, root = self.validation()
        report = paired_controls.compare(
            self.baseline(),
            self.artifact,
            manifest,
            root,
            "validation",
            Path(os.environ["UCHARDET_STATIC_LIBRARY"]),
            os.environ.get("UCHARDET_PROBE_CXX", "c++"),
        )
        for profile in report["profiles"].values():
            self.assertEqual(len(profile["documents"]), 2)
            self.assertEqual(profile["summary"]["cp1252"]["documents"], 1)
            self.assertEqual(profile["summary"]["utf-8"]["documents"], 1)
            self.assertEqual(profile["paired_separation"]["finite_distinct_pairs"], 1)
            self.assertEqual(
                profile["control_decodability_strata"]["cp1252_decodable"]["total_pairs"], 1
            )
            self.assertEqual(profile["summary"]["utf-8"]["stopped_before_filtered_end"], 0)


if __name__ == "__main__":
    unittest.main()
