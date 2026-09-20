# SPDX-License-Identifier: MIT
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import paris_training as training
import paris_stories as pilot
import test_paris_stories as fixtures
from framework import content_hash, generate


class ParisTrainingTests(unittest.TestCase):
    def test_recording_assignment_is_order_independent(self):
        identities = ["3" * 64, "1" * 64, "2" * 64]
        expected = {"1" * 64: "tuning", "2" * 64: "training", "3" * 64: "training"}
        self.assertEqual(training.recording_splits(identities, 1), expected)
        self.assertEqual(training.recording_splits(reversed(identities), 1), expected)
        self.assertEqual(set(training.recording_splits(identities, 0).values()), {"training"})
        for invalid in (True, -1, 3, 4, 1.0):
            with self.assertRaises(ValueError):
                training.recording_splits(identities, invalid)
        with self.assertRaises(ValueError):
            training.recording_splits(["1" * 64, "1" * 64], 1)

    def test_tuning_recipe_preserves_recordings_and_excludes_old_models(self):
        data = self.raw + fixtures.sentence("extra_1", "Autre texte.", "separate").encode()
        (self.root / training.TEXT_FILE).write_bytes(data)
        self.recipe["files"][-1] = [training.TEXT_FILE, pilot.digest(data), len(data)]
        self.recipe["tuning_recordings"] = 1
        report = self.ingest()
        config = json.loads((self.root / "output/config.json").read_text())
        self.assertEqual({s["split"] for s in config["sources"]}, {"training", "tuning"})
        self.assertEqual(report["profile"], training.SPLIT_PROFILE)
        self.assertFalse(report["previous_training_models_reusable"])
        self.assertEqual(sum(len(s["sentence_ids"]) for s in config["sources"]), 2)
        for source in config["sources"]:
            self.assertEqual(source["split"], report["recording_assignments"][source["recording_identity_sha256"]])

    def test_tuning_cannot_take_all_recordings(self):
        self.recipe["tuning_recordings"] = 1
        with self.assertRaisesRegex(ValueError, "leave at least one"):
            self.ingest()
        self.assertFalse((self.root / "output").exists())

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.raw = fixtures.sentence("train_1", "Café et thé.", "train-recording").encode()
        self.files = {"README.md": b"Synthetic notice", "LICENSE.txt": b"Synthetic license",
                      training.TEXT_FILE: self.raw}
        for name, data in self.files.items():
            (self.root / name).write_bytes(data)
        self.validation = dict(schema_version=1, sources=[dict(
            id="validation-document", path="not-opened.txt", language="fr", kind="natural",
            license="CC-BY-SA-4.0", license_reference="https://example.org/license",
            revision="1" * 40, origin="parisstories:recording:validation",
            sha256="a" * 64, split="validation", sentence_ids=["ParisStories_val_1"],
        )])
        self.validation["content_hash"] = content_hash(self.validation)
        self.recipe = dict(recipe_version=1, repository=pilot.REPOSITORY, revision="1" * 40,
                           license="CC-BY-SA-4.0", upstream_split="train",
                           validation_manifest_content_hash=self.validation["content_hash"],
                           files=[[name, pilot.digest(data), len(data)] for name, data in self.files.items()])

    def ingest(self, output="output"):
        return training.ingest(self.recipe, self.root, self.validation, self.root / output)

    def test_training_only_metadata_and_roundtrip(self):
        with patch.object(training.urllib.request, "build_opener", side_effect=AssertionError("network")):
            result = self.ingest()
        self.assertEqual((result["documents"], result["sentences"]), (1, 1))
        config = json.loads((self.root / "output/config.json").read_text())
        self.assertEqual(config["sources"][0]["split"], "training")
        self.assertEqual(config["sources"][0]["upstream_split"], "train")
        self.assertEqual(config["byte_limits"], [None])
        manifest = generate(config, self.root / "output", self.root / "generated")
        self.assertEqual(len(manifest["samples"]), 2)
        self.assertFalse((self.root / "not-opened.txt").exists())

    def test_reproducible_and_refuses_overwrite(self):
        self.ingest("a")
        self.ingest("b")
        for path in (self.root / "a").rglob("*"):
            if path.is_file():
                self.assertEqual(path.read_bytes(), (self.root / "b" / path.relative_to(self.root / "a")).read_bytes())
        with self.assertRaises(ValueError):
            self.ingest("a")

    def test_split_overlap_rejected_before_publication(self):
        for field, value in (
            ("origin", "parisstories:recording:" + pilot.digest(b"https://api.nakala.fr/data/train-recording")),
            ("sha256", pilot.digest("Café et thé.\n".encode())),
            ("sentence_ids", ["ParisStories_train_1"]),
        ):
            with self.subTest(field=field):
                validation = copy.deepcopy(self.validation)
                validation["sources"][0][field] = value
                validation["content_hash"] = content_hash(validation)
                recipe = self.recipe | {"validation_manifest_content_hash": validation["content_hash"]}
                with self.assertRaises(ValueError):
                    training.ingest(recipe, self.root, validation, self.root / "rejected")
                self.assertFalse((self.root / "rejected").exists())

    def test_reference_or_input_corruption_rejected(self):
        self.recipe["validation_manifest_content_hash"] = "f" * 64
        with self.assertRaises(ValueError):
            self.ingest()
        self.recipe["validation_manifest_content_hash"] = self.validation["content_hash"]
        (self.root / training.TEXT_FILE).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            self.ingest()
        self.assertFalse((self.root / "output").exists())

    def test_recording_quarantine_requires_actual_validation_overlap(self):
        identity = pilot.digest(b"https://api.nakala.fr/data/train-recording")
        self.recipe["quarantine_recording_ids"] = [identity]
        with self.assertRaisesRegex(ValueError, "not a validation overlap"):
            self.ingest()
        self.validation["sources"][0]["origin"] = "parisstories:recording:" + identity
        self.validation["content_hash"] = content_hash(self.validation)
        self.recipe["validation_manifest_content_hash"] = self.validation["content_hash"]
        extra = fixtures.sentence("extra_1", "Autre texte.", "separate").encode()
        data = self.raw + extra
        (self.root / training.TEXT_FILE).write_bytes(data)
        self.recipe["files"][-1] = [training.TEXT_FILE, pilot.digest(data), len(data)]
        report = self.ingest()
        self.assertEqual(report["sentences"], 1)
        self.assertEqual(report["quarantined_records"][0]["reason"], "VALIDATION_RECORDING_OVERLAP")
        config = json.loads((self.root / "output/config.json").read_text())
        self.assertEqual(config["sources"][0]["sentence_ids"], ["ParisStories_extra_1"])

    def test_validation_and_test_cannot_be_training_recipes(self):
        for split in ("dev", "test", "independent"):
            with self.assertRaises(ValueError):
                training.validate_recipe(self.recipe | {"upstream_split": split})
        recipe = copy.deepcopy(self.recipe)
        recipe["files"][-1][0] = "fr_parisstories-ud-test.conllu"
        with self.assertRaises(ValueError):
            training.validate_recipe(recipe)

    def test_cache_requires_no_network(self):
        with patch.object(training.urllib.request, "build_opener") as factory:
            result = training.fetch(self.recipe, self.root)
            factory.return_value.open.assert_not_called()
        self.assertEqual(result["transferred_bytes"], 0)

    def test_parser_default_limit_is_preserved(self):
        raw = self.raw + b"\n" * pilot.MAX_FILE_BYTES
        with self.assertRaises(ValueError):
            pilot.documents(raw)
        self.assertEqual(len(pilot.documents(raw, max_bytes=training.MAX_FILE_BYTES)), 1)
        for budget in (0, True, training.MAX_FILE_BYTES + 1):
            with self.assertRaises(ValueError):
                pilot.documents(self.raw, max_bytes=budget)

    def test_quarantine_is_explicit_and_does_not_guess_recording(self):
        missing = fixtures.sentence("missing_1", "Texte.", "missing").replace(
            "# sound_url = https://api.nakala.fr/data/missing\n", ""
        ).encode()
        admitted, report = training.partition(self.raw + missing, ["ParisStories_missing_1"])
        self.assertEqual(len(pilot.documents(admitted)), 1)
        self.assertEqual(report[0]["reason"], "MISSING_RECORDING_IDENTITY")
        with self.assertRaises(ValueError):
            pilot.documents(training.partition(self.raw + missing, [])[0])
        for data, identities in (
            (self.raw, ["ParisStories_missing_1"]),
            (self.raw, ["ParisStories_train_1"]),
            (self.raw + missing * 2, ["ParisStories_missing_1"]),
        ):
            with self.assertRaises(ValueError):
                training.partition(data, identities)


if __name__ == "__main__":
    unittest.main()
