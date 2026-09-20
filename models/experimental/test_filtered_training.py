# SPDX-License-Identifier: MIT
import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import filtered_training as filtered
from framework import generate
from model import canonical, digest, write_idempotent
from sequence_contract import content_hash
from sequence_training import count_document


def observation(raw, retained):
    def statistics(data):
        result = count_document(data)
        result["bytes"] = result.pop("byte_count")
        return result

    return dict(
        schema="sbcs-filter-profile-v1",
        chunk_size=0,
        raw=statistics(raw),
        filtered=statistics(retained),
        calls=[[len(raw), len(retained)]] if raw else [],
    )


class FilteredTrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = b"plain caf\xe9 text"
        text = self.data.decode("cp1252").encode("utf-8")
        (self.root / "source.txt").write_bytes(text)
        source = dict(
            id="one",
            path="source.txt",
            language="fr",
            license="MIT",
            license_reference="corpus/LICENSES/MIT.txt",
            revision="synthetic-v1",
            origin="synthetic:filtered-training",
            kind="synthetic",
            sha256=digest(text),
            split="training",
        )
        self.manifest = generate(
            dict(sources=[source], encodings=["cp1252"], byte_limits=[None], formats=["text"]),
            self.root,
            self.root / "corpus",
        )
        self.binary = self.root / "binary"
        self.binary.write_bytes(b"mock binary fingerprint; never executed")
        self.observation = observation(self.data, b"caf\xe9 ")
        with patch.object(filtered, "observe", return_value=self.observation):
            self.artifact = filtered.train(self.manifest, self.root / "corpus", "fr", self.binary)

    def test_filtered_counts_not_identity_and_idempotence(self):
        filtered.validate(self.artifact)
        self.assertFalse(self.artifact["contract"]["keep_english_letters"])
        self.assertEqual(self.artifact["contract"]["frequent_character_count"], 4)
        self.assertEqual(self.artifact["audit"]["letter_pair_mass"], 3)
        self.assertEqual(self.artifact["native_binary_sha256"], digest(self.binary.read_bytes()))
        path = self.root / "artifact.json"
        write_idempotent(path, canonical(self.artifact))
        stamp = path.stat().st_mtime_ns
        write_idempotent(path, canonical(self.artifact))
        self.assertEqual(stamp, path.stat().st_mtime_ns)
        with self.assertRaises(ValueError):
            write_idempotent(path, b"different")

    def test_invalid_observation_policy_and_counts(self):
        for mutate in (
            lambda o: o.__setitem__("chunk_size", 1),
            lambda o: o.__setitem__("chunk_size", False),
            lambda o: o.__setitem__("calls", [[15, True]]),
            lambda o: o.__setitem__("calls", [[7, 2], [8, 3]]),
            lambda o: o["filtered"].__setitem__("bytes", 6),
            lambda o: o["filtered"]["pairs"].clear(),
            lambda o: o.__setitem__("schema", "unknown"),
        ):
            value = copy.deepcopy(self.observation)
            mutate(value)
            with self.assertRaises(ValueError):
                filtered.check_observation(value)
        self.assertEqual(filtered.check_observation(observation(b"", b""))[1]["byte_count"], 0)

    def test_recomputed_tampering_rejected(self):
        for mutate in (
            lambda a: a["contract"].__setitem__("keep_english_letters", True),
            lambda a: a["audit"].__setitem__("letter_pair_mass", 100),
            lambda a: a["documents"][0]["source"].__setitem__("split", "validation"),
            lambda a: a["documents"][0]["source"].__setitem__("language", "de"),
            lambda a: a["spec"].__setitem__("chunk_size", 7),
            lambda a: a.__setitem__("native_binary_sha256", "invalid"),
            lambda a: a.__setitem__("dependencies", {}),
        ):
            value = copy.deepcopy(self.artifact)
            mutate(value)
            value["content_hash"] = content_hash(value)
            with self.assertRaises(ValueError):
                filtered.validate(value)

    def test_independent_refused_before_corpus_reads(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["sources"][0]["split"] = "independent"
        with patch.object(filtered, "select") as select:
            with self.assertRaisesRegex(ValueError, "sealed"):
                filtered.train(manifest, self.root, "fr", self.binary)
            select.assert_not_called()

    def test_limits_before_execution(self):
        with patch.object(filtered.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "65536"):
                filtered.observe(self.binary, b"a" * 65537)
            run.assert_not_called()

    def test_observe_verifies_raw_and_timeout(self):
        bad = observation(b"different", b"diff")
        with patch.object(
            filtered.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, stdout=canonical(bad)),
        ) as run:
            with self.assertRaisesRegex(ValueError, "raw statistics"):
                filtered.observe(self.binary, self.data)
            self.assertEqual(run.call_args.kwargs["timeout"], 10)
        with patch.object(
            filtered.subprocess, "run", side_effect=subprocess.TimeoutExpired("test", 10)
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                filtered.observe(self.binary, self.data)

    @unittest.skipUnless(
        os.environ.get("UCHARDET_FILTER_PROFILE"), "native filter tool not configured"
    )
    def test_real_native_training_regeneration(self):
        binary = Path(os.environ["UCHARDET_FILTER_PROFILE"])
        result = filtered.train(self.manifest, self.root / "corpus", "fr", binary)
        self.assertEqual(result["documents"][0]["observation"], self.observation)
        self.assertEqual(result, filtered.train(self.manifest, self.root / "corpus", "fr", binary))
        # generated sample paths are relative to the generated corpus directory.
        manifest = self.root / "corpus" / "manifest.json"
        manifest.write_text(json.dumps(self.manifest), encoding="utf-8")
        artifact = self.root / "artifact.json"
        artifact.write_bytes(canonical(result))
        import sys

        subprocess.run(
            [
                sys.executable,
                str(Path(filtered.__file__)),
                "validate",
                str(artifact),
                "--manifest",
                str(manifest),
                "--binary",
                str(binary),
            ],
            check=True,
            timeout=30,
        )


if __name__ == "__main__":
    unittest.main()
