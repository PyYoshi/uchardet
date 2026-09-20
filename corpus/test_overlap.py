# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import tempfile
import unittest
from fractions import Fraction
from unittest.mock import patch

from framework import content_hash, digest
from overlap import audit, normalize


class OverlapTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def manifest(self, name, text, split="validation"):
        root = self.root / name
        root.mkdir()
        raw = text.encode()
        (root / "source.txt").write_bytes(raw)
        source = dict(id=name, path="source.txt", language="fr", license="MIT",
                      license_reference="fixture", revision="1", origin=name,
                      sha256=digest(raw), split=split, kind="synthetic",
                      byte_length=len(raw), character_length=len(text))
        manifest = dict(schema_version=1, sources=[source], samples=[])
        manifest["content_hash"] = content_hash(manifest)
        path = root / "manifest.json"
        path.write_text(json.dumps(manifest))
        return path

    def test_normalization(self):
        self.assertEqual(normalize(" ＣＡＦÉ\t Straße\n"), "café strasse")

    def test_cross_split_equal_and_order_independent(self):
        a = self.manifest("a", "Café text", "training")
        b = self.manifest("b", "Ｃafé  TEXT", "validation")
        first = audit([a, b])
        self.assertEqual(first, audit([b, a]))
        self.assertEqual(first["findings"][0]["kind"], "normalized_equal")
        self.assertTrue(first["findings"][0]["cross_split"])

    def test_near_not_equal(self):
        a = self.manifest("a", "This is a sufficiently long shared document sentence ending A")
        b = self.manifest("b", "This is a sufficiently long shared document sentence ending B")
        self.assertEqual(audit([a, b])["findings"][0]["kind"], "near_duplicate_candidate")

    def test_short_and_empty(self):
        paths = [self.manifest("a", ""), self.manifest("b", " "),
                 self.manifest("c", "a"), self.manifest("d", "b")]
        self.assertEqual(audit(paths)["findings"], [])

    def test_holdout_body_never_opened(self):
        path = self.manifest("a", "unread", "independent")
        (path.parent / "source.txt").unlink()
        report = audit([path])
        self.assertEqual(len(report["skipped_independent"]), 1)
        self.assertEqual(report["sources"], [])

    def test_source_tampering(self):
        path = self.manifest("a", "before")
        (path.parent / "source.txt").write_text("after")
        with self.assertRaisesRegex(ValueError, "hash or length"):
            audit([path])

    def test_known_metadata_leakage_rejected(self):
        a = self.manifest("a", "identical", "training")
        b = self.manifest("b", "identical", "validation")
        with self.assertRaisesRegex(ValueError, "leakage"):
            audit([a, b])

    def test_duplicate_manifest(self):
        path = self.manifest("a", "abc")
        with self.assertRaisesRegex(ValueError, "duplicate manifest"):
            audit([path, path])

    def test_threshold(self):
        path = self.manifest("a", "abc")
        for threshold in (Fraction(0), Fraction(2)):
            with self.assertRaises(ValueError):
                audit([path], threshold)

    def test_budgets(self):
        path = self.manifest("a", "abc")
        with patch("overlap.MAX_SOURCE_BYTES", 2), self.assertRaisesRegex(ValueError, "budget"):
            audit([path])
        with patch("overlap.MAX_SOURCES", 0), self.assertRaises(ValueError):
            audit([path])


if __name__ == "__main__":
    unittest.main()
