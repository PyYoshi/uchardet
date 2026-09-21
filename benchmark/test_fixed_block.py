# SPDX-License-Identifier: MIT
"""Small valid-input pilot contracts and metadata rejection tests."""

import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fixed_block_compare as comparison


class FrozenInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sample = self.root / "sample.bin"
        self.sample.write_bytes(b"plain ASCII")
        self.manifest = dict(
            samples=[
                dict(
                    id="example",
                    path="sample.bin",
                    split="tuning",
                    boundary="complete",
                    encoding="cp1252",
                    sha256=comparison.sha(self.sample),
                )
            ]
        )

    def run_rejected(self, manifest=None, mutate_previous=False, split="tuning"):
        manifest = copy.deepcopy(manifest or self.manifest)
        previous = dict(
            manifest_hash=comparison.manifest_hash(manifest),
            documents=[
                dict(
                    sample_id="example",
                    sample_sha256=comparison.sha(self.sample),
                    byte_length=11,
                    encoding="cp1252",
                )
            ],
        )
        if split == "validation":
            previous["corpus_content_hash"] = previous.pop("manifest_hash")
            previous["split"] = split
            row = previous["documents"][0]
            row["sample_encoding"] = row.pop("encoding")
            row["observations"] = {"legacy": {}}
        frozen = comparison.content_hash(previous)
        previous["content_hash"] = frozen
        if mutate_previous:
            previous["documents"][0]["byte_length"] += 1
        manifest_path = self.root / "manifest.json"
        previous_path = self.root / "previous.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        previous_path.write_text(json.dumps(previous), encoding="utf-8")
        # Synthetic frozen fixture only; the production constant is never changed.
        with (
            patch.object(comparison, "FROZEN" if split == "tuning" else "VALIDATION", frozen),
            patch.object(comparison.subprocess, "run") as run,
        ):
            with self.assertRaises(ValueError):
                comparison.run(manifest_path, previous_path, self.sample, self.sample, split)
            run.assert_not_called()

    def test_changed_frozen_report_rejected_before_execution(self):
        self.run_rejected(mutate_previous=True)

    def test_non_tuning_and_incomplete_metadata_rejected(self):
        for field, value in (
            ("split", "independent"),
            ("boundary", "byte-truncated"),
            ("encoding", "utf-8"),
            ("sha256", "0" * 64),
        ):
            manifest = copy.deepcopy(self.manifest)
            manifest["samples"][0][field] = value
            with self.subTest(field=field):
                self.run_rejected(manifest)

    def test_duplicate_id_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["samples"] *= 2
        self.run_rejected(manifest)

    def test_path_outside_corpus_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["samples"][0]["path"] = "../not-a-corpus-sample"
        self.run_rejected(manifest)

    def test_validation_cannot_use_tuning_or_independent_samples(self):
        for split in ("tuning", "independent"):
            manifest = copy.deepcopy(self.manifest)
            manifest["samples"][0]["split"] = split
            self.run_rejected(manifest, split="validation")

    def test_modified_validation_report_rejected(self):
        self.run_rejected(mutate_previous=True, split="validation")

    def test_independent_mode_rejected_before_reading(self):
        with patch.object(Path, "read_text") as read:
            with self.assertRaises(ValueError):
                comparison.run(self.sample, self.sample, self.sample, self.sample, "independent")
            read.assert_not_called()


@unittest.skipUnless(os.environ.get("UCHARDET_FIXED_BLOCK"), "set UCHARDET_FIXED_BLOCK")
class FixedBlockCliTests(unittest.TestCase):
    def invoke(self, args, inputs):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for index, data in enumerate(inputs):
                path = Path(directory) / str(index)
                path.write_bytes(data)
                paths.append(str(path))
            return subprocess.run(
                [os.environ["UCHARDET_FIXED_BLOCK"], *map(str, args), *paths],
                capture_output=True,
                text=True,
                timeout=10,
            )

    def test_invalid_parameters(self):
        for block, limit in ((0, 4096), (4097, 4096), (64, 4097), (-1, 1), ("7x", 1)):
            with self.subTest(block=block, limit=limit):
                result = self.invoke([block, limit, "fresh", 0], [b"ASCII"])
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_limit_and_fresh_reuse(self):
        inputs = [b"", b"plain ASCII", "café et thé".encode("cp1252"), b"a" * 65]
        for limit in (0, 1, 63, 64, 65, 4096):
            fresh = self.invoke([64, limit, "fresh", 1], inputs)
            reused = self.invoke([64, limit, "reuse", 1], inputs)
            self.assertEqual(fresh.returncode, 0, fresh.stderr)
            self.assertEqual(reused.returncode, 0, reused.stderr)
            self.assertEqual(fresh.stdout, reused.stdout)
            for line, data in zip(fresh.stdout.splitlines(), inputs):
                record = json.loads(line)
                self.assertEqual(record["core_processed_bytes"], min(len(data), limit))

    def test_input_cap(self):
        result = self.invoke([64, 4096, "fresh", 0], [b"a" * 4097])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exceeds 4096", result.stderr)


if __name__ == "__main__":
    unittest.main()
