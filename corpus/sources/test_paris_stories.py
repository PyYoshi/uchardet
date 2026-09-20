# SPDX-License-Identifier: MIT
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import paris_stories as pilot
from framework import generate


def sentence(identifier, text, recording="one"):
    return (f"# sent_id = ParisStories_{identifier}\n# text = {text}\n"
            f"# sound_url = https://api.nakala.fr/data/{recording}\n"
            "1\tx\tx\tX\t_\t_\t0\troot\t_\t_\n\n")


class ParisStoriesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.raw = (sentence("a_1", "Café.") + sentence("a_2bis", "Ça va ?") +
                    sentence("b_1", "Emoji 😀", "two")).encode()
        self.files = {"README.md": b"Synthetic notice", "LICENSE.txt": b"Synthetic license",
                      pilot.TEXT_FILE: self.raw}
        self.recipe = dict(recipe_version=1, repository=pilot.REPOSITORY, revision="1" * 40,
                           license="CC-BY-SA-4.0", upstream_split="dev",
                           files=[[name, pilot.digest(data), len(data)] for name, data in self.files.items()])
        for name, data in self.files.items():
            (self.root / name).write_bytes(data)

    def test_recording_group_and_sentence_order(self):
        groups = pilot.documents(self.raw)
        self.assertEqual(len(groups), 2)
        first = groups[pilot.digest(b"https://api.nakala.fr/data/one")]
        self.assertEqual(first["sentence_ids"], ["ParisStories_a_1", "ParisStories_a_2bis"])
        self.assertEqual(first["texts"], ["Café.", "Ça va ?"])

    def test_offline_ingest_and_strict_generation(self):
        with patch.object(pilot.urllib.request, "build_opener", side_effect=AssertionError("network")):
            report = pilot.ingest(self.recipe, self.root, self.root / "output")
        self.assertEqual((report["documents"], report["sentences"]), (2, 3))
        config = json.loads((self.root / "output/config.json").read_text())
        self.assertTrue(all(s["split"] == "validation" for s in config["sources"]))
        self.assertEqual(len({s["origin"] for s in config["sources"]}), 2)
        self.assertEqual((self.root / "output/notices/LICENSE.txt").read_bytes(), self.files["LICENSE.txt"])
        manifest = generate(config, self.root / "output", self.root / "generated",
                            failure_policy="record-and-continue")
        self.assertEqual(manifest["generation_report"]["counts"],
                         {"attempted": 16, "successful": 12, "skipped": 4})

    def test_reproducible_and_no_overwrite(self):
        pilot.ingest(self.recipe, self.root, self.root / "a")
        pilot.ingest(self.recipe, self.root, self.root / "b")
        for file in (self.root / "a").rglob("*"):
            if file.is_file():
                self.assertEqual(file.read_bytes(), (self.root / "b" / file.relative_to(self.root / "a")).read_bytes())
        with self.assertRaises(ValueError):
            pilot.ingest(self.recipe, self.root, self.root / "a")

    def test_corruption_before_output_creation(self):
        (self.root / pilot.TEXT_FILE).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            pilot.ingest(self.recipe, self.root, self.root / "output")
        self.assertFalse((self.root / "output").exists())

    def test_cached_fetch_has_no_network(self):
        with patch.object(pilot.urllib.request, "build_opener") as factory:
            result = pilot.fetch(self.recipe, self.root)
            factory.return_value.open.assert_not_called()
        self.assertEqual(result["transferred_bytes"], 0)

    def test_fetch_fixed_urls_only(self):
        with patch.object(pilot.urllib.request, "build_opener") as factory:
            factory.return_value.open.side_effect = [io.BytesIO(d) for d in self.files.values()]
            result = pilot.fetch(self.recipe, self.root / "new")
            urls = [call.args[0] for call in factory.return_value.open.call_args_list]
        self.assertEqual(result["transferred_bytes"], sum(map(len, self.files.values())))
        self.assertTrue(all(url.startswith(f"https://raw.githubusercontent.com/{pilot.REPOSITORY}/{'1' * 40}/") for url in urls))
        self.assertFalse(any("nakala" in url for url in urls))

    def test_recipe_rejects_other_split_or_source(self):
        for field, value in (("upstream_split", "test"), ("revision", "master"),
                             ("repository", "other/repo"), ("license", "MIT")):
            recipe = copy.deepcopy(self.recipe)
            recipe[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                pilot.validate_recipe(recipe)

    def test_duplicate_sentence_or_metadata(self):
        for raw in ((sentence("a_1", "A") * 2).encode(),
                    sentence("a_1", "A").replace("# text = A", "# text = A\n# text = B").encode()):
            with self.assertRaises(ValueError):
                pilot.documents(raw)

    def test_missing_identity_or_token_rows(self):
        raw = sentence("a_1", "A")
        for fragment in ("# sound_url = https://api.nakala.fr/data/one\n",
                         "1\tx\tx\tX\t_\t_\t0\troot\t_\t_\n"):
            with self.assertRaises(ValueError):
                pilot.documents(raw.replace(fragment, "").encode())

    def test_empty_budget_and_bad_columns(self):
        for raw in (b"", b"\xff", b"x" * (pilot.MAX_FILE_BYTES + 1), b"1\tx\n"):
            with self.assertRaises((ValueError, UnicodeError)):
                pilot.documents(raw)

    def test_final_sentence_without_blank_separator(self):
        self.assertEqual(pilot.documents(self.raw), pilot.documents(self.raw.rstrip(b"\n")))


if __name__ == "__main__":
    unittest.main()
