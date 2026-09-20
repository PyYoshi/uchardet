# SPDX-License-Identifier: MIT
"""Synthetic fixtures exercise infrastructure, not natural-language accuracy."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from framework import content_hash, digest, encode_variant, generate, safe_path, validate


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.text = "Test synthétique: café & thé.\n"
        self.raw = self.text.encode("utf-8")
        (self.root / "input.txt").write_bytes(self.raw)
        self.config = {"sources": [{"id": "synthetic", "path": "input.txt", "language": "fr",
            "license": "MIT", "license_reference": "corpus/LICENSES/MIT.txt",
            "revision": "fixture-v1", "origin": "synthetic:corpus-test-v1", "kind": "synthetic",
            "sha256": digest(self.raw), "split": "validation"}], "encodings": ["utf-8", "cp1252"],
            "byte_limits": [None, 16, 64], "boundaries": ["complete", "truncated"],
            "formats": ["text", "html-clean", "html-declared", "html-mismatched"]}

    def generate(self, config=None, name="out"):
        return generate(config or self.config, self.root, self.root / name)

    def assert_invalid(self, manifest):
        manifest["content_hash"] = content_hash(manifest)
        with self.assertRaises(ValueError):
            validate(manifest, self.root / "out")

    def test_deterministic_manifest_and_bytes(self):
        first, second = self.generate(name="one"), self.generate(name="two")
        self.assertEqual(first, second)
        for sample in first["samples"]:
            self.assertEqual((self.root / "one" / sample["path"]).read_bytes(),
                             (self.root / "two" / sample["path"]).read_bytes())
        first["generated_at"] = "2026-09-20T00:00:00Z"
        self.assertEqual(first["content_hash"], content_hash(first))

    def test_missing_rights_rejected(self):
        for key in ("license", "license_reference", "revision", "origin", "sha256"):
            with self.subTest(key=key):
                config = copy.deepcopy(self.config)
                del config["sources"][0][key]
                with self.assertRaises(ValueError):
                    self.generate(config)
                self.assertFalse((self.root / "out").exists())

    def test_source_hash_rejected(self):
        self.config["sources"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash"):
            self.generate()

    def test_traversal_and_symlink_rejected(self):
        for path in ("../input.txt", "/etc/passwd", "..\\input.txt"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_path(self.root, path)
        (self.root / "escape").symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            safe_path(self.root, "escape/outside")

    def test_variant_split_leakage(self):
        manifest = self.generate()
        manifest["samples"][0]["split"] = "training"
        self.assert_invalid(manifest)

    def test_renamed_source_split_leakage(self):
        manifest = self.generate()
        original = manifest["sources"][0]
        manifest["sources"].append(dict(original, id="renamed", split="training"))
        self.assert_invalid(manifest)

    def test_origin_split_leakage(self):
        manifest = self.generate()
        source = dict(manifest["sources"][0], id="revision2", path="sources/revision2.txt", split="training")
        data = b"Different revision"
        (self.root / "out" / source["path"]).write_bytes(data)
        source.update(sha256=digest(data), byte_length=len(data), character_length=len(data))
        manifest["sources"].append(source)
        self.assert_invalid(manifest)

    def test_strict_unencodable_and_non_roundtrip(self):
        with self.assertRaises(UnicodeEncodeError):
            encode_variant("a\U0001f600", "cp1252", 1, "complete")
        with self.assertRaises(ValueError):
            encode_variant("\u00a5", "shift_jis", None, "complete")
        with self.assertRaises(ValueError):
            encode_variant("abc", "utf-8", True, "complete")

    def test_stateful_finalization_and_bom_sizes(self):
        for encoding in ("iso2022_jp", "utf-16", "utf-32", "utf-8-sig"):
            for size in range(1, 32):
                data, count = encode_variant("日本語abc", encoding, size, "complete")
                self.assertLessEqual(len(data), size)
                if data:
                    self.assertEqual(data.decode(encoding), "日本語abc"[:count])
                    self.assertEqual(data, "日本語abc"[:count].encode(encoding))

    def test_intentional_truncation_is_not_complete_prefix(self):
        data, chars = encode_variant("é", "utf-8", 1, "truncated")
        self.assertEqual(data, b"\xc3")
        self.assertIsNone(chars)
        with self.assertRaises(UnicodeDecodeError):
            data.decode("utf-8")

    def test_incremental_prefix_matches_exhaustive_reference(self):
        for encoding, text in (("iso2022_jp", "日本語abc日本"), ("utf-16", "日本語abc"),
                               ("utf-32", "日本語abc"), ("utf-8-sig", "éabc"),
                               ("hz", "中文abc中文"), ("cp1252", "café")):
            for size in range(1, len(text.encode(encoding)) + 1):
                expected = b""
                for end in range(len(text) + 1):
                    candidate = text[:end].encode(encoding)
                    if len(candidate) <= size:
                        expected = candidate
                actual, _ = encode_variant(text, encoding, size, "complete")
                self.assertEqual(actual, expected, (encoding, size))

    def test_html_groundtruth_independent_of_declaration(self):
        manifest = self.generate()
        for sample in manifest["samples"]:
            if sample["format"] == "html-mismatched":
                self.assertNotEqual(sample["encoding"], sample["declared_encoding"])
        changed = copy.deepcopy(manifest)
        changed["samples"][0]["declared_encoding"] = "fabricated"
        self.assert_invalid(changed)

    def test_tampering_and_sizes(self):
        manifest = self.generate()
        manifest["samples"][0]["character_length"] = 1000
        self.assert_invalid(manifest)
        manifest = json.loads((self.root / "out/manifest.json").read_text())
        target = self.root / "out" / manifest["samples"][0]["path"]
        target.write_bytes(b"tampered")
        self.assert_invalid(manifest)

    def test_no_overwrite(self):
        self.generate()
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.generate()


if __name__ == "__main__":
    unittest.main()
