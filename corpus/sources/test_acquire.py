# SPDX-License-Identifier: MIT
import copy
import json
from pathlib import Path
import tempfile
import unittest

from acquire import ingest, paragraphs, validate_recipe, write_once
from framework import digest


class AcquisitionTests(unittest.TestCase):
    def test_frozen_recipe(self):
        recipe = json.loads(Path(__file__).with_name("rust-book-pilot.json").read_text())
        self.assertEqual(validate_recipe(recipe), 381359)
        recipe["repositories"][0]["revision"] = "main"
        with self.assertRaises(ValueError):
            validate_recipe(recipe)

    def test_notices_comments_code_not_prose(self):
        text = '# Title\n\n<!-- English reference -->\n\nTexte français.\n\n```rust\nlet x = 1;\n```\n\nSuite.\n\n[link]: example\n'
        self.assertEqual(paragraphs(text), ["Texte français.", "Suite."])

    def test_idempotent_write_and_conflict(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "file"
            write_once(path, b"data")
            before = path.stat().st_mtime_ns
            write_once(path, b"data")
            self.assertEqual(before, path.stat().st_mtime_ns)
            with self.assertRaises(ValueError):
                write_once(path, b"other")

    def test_ingestion_reports_excluded_paragraphs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "raw/fr"
            raw.mkdir(parents=True)
            blobs = {"LICENSE-MIT": b"test notice", "LICENSE-APACHE": b"test notice", "COPYRIGHT": b"test attribution",
                     "chapter.md": "Café.\n\nEmoji 😀.\n".encode("utf-8")}
            files = []
            for path, data in blobs.items():
                (raw / path).write_bytes(data)
                files.append([path, digest(data), len(data)])
            recipe = dict(recipe_version=1, license_choice="MIT", chapters=[["chapter.md", "training"]],
                repositories=[dict(language="fr", repository="example/book", revision="a" * 40,
                                   prefix=".", legacy_encoding="cp1252", files=files)])
            # Keep recipe paths exactly consistent, including the explicit prefix.
            recipe["repositories"][0]["files"][-1][0] = "./chapter.md"
            ingest(recipe, root / "raw", root / "out")
            config = json.loads((root / "out/fr-cp1252.json").read_text())
            source = config["sources"][0]
            self.assertEqual(source["excluded_paragraphs"], 1)
            self.assertEqual(source["origin"], "rust-book:chapter.md")
            self.assertTrue(source["license_reference"].startswith("https://github.com/"))
            self.assertEqual((root / "out" / source["path"]).read_text(), "Café.\n")
            ingest(recipe, root / "raw", root / "out")
            (raw / "chapter.md").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                ingest(recipe, root / "raw", root / "other")

    def test_recipe_path_and_size_rejected(self):
        original = json.loads(Path(__file__).with_name("rust-book-pilot.json").read_text())
        for bad in (["../escape", "a" * 64, 1], ["file", "a" * 64, 2**30]):
            recipe = copy.deepcopy(original)
            recipe["repositories"][0]["files"][0] = bad
            with self.assertRaises(ValueError):
                validate_recipe(recipe)


if __name__ == "__main__":
    unittest.main()
