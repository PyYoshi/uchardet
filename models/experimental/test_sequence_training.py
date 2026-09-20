# SPDX-License-Identifier: MIT
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from model import canonical, digest, write_idempotent
from framework import content_hash as corpus_hash, generate
from sequence_contract import content_hash, validate as validate_contract
from sequence_training import binary32_ratio, character_classes, count_document, derive, train, validate


class SequenceTrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        sources = []
        for name, text, split in (("one", "abba café", "training"), ("two", "baba thé", "training"),
                                  ("heldout", "not training", "validation")):
            data = text.encode()
            (self.root / f"{name}.txt").write_bytes(data)
            sources.append(dict(id=name, path=f"{name}.txt", language="fr", license="MIT",
                license_reference="corpus/LICENSES/MIT.txt", revision="artificial-v1", origin=f"synthetic:{name}",
                kind="synthetic", sha256=digest(data), split=split))
        self.manifest = generate(dict(sources=sources, encodings=["cp1252"], byte_limits=[None, 3],
                                     formats=["text", "html-clean"]), self.root, self.root / "corpus")
        self.artifact = train(self.manifest, self.root / "corpus", "fr")

    def test_determinism_idempotence_and_contract(self):
        self.assertEqual(canonical(self.artifact), canonical(train(self.manifest, self.root / "corpus", "fr")))
        validate(self.artifact)
        validate_contract(self.artifact["contract"])
        path = self.root / "artifact.json"
        write_idempotent(path, canonical(self.artifact))
        before = path.stat().st_mtime_ns
        write_idempotent(path, canonical(self.artifact))
        self.assertEqual(before, path.stat().st_mtime_ns)
        with self.assertRaises(ValueError):
            write_idempotent(path, b"different")

    def test_training_selection_and_document_boundaries(self):
        self.assertEqual(len(self.artifact["documents"]), 2)
        self.assertTrue(all(d["source"]["split"] == "training" for d in self.artifact["documents"]))
        for d in self.artifact["documents"]:
            self.assertEqual(sum(n for _, _, n in d["counts"]["pairs"]), d["counts"]["byte_count"] - 1)
        with self.assertRaisesRegex(ValueError, "adjacent"):
            derive([{"counts": count_document(b"a")}, {"counts": count_document(b"b")}])

    def test_character_classes_and_order_ties(self):
        classes = character_classes()
        for byte, category in ((0x81, 255), (10, 252), (13, 252), (0, 254), (48, 251), (32, 253), (0xe9, "letter")):
            self.assertEqual(classes[byte], category)
        fields, _ = derive([{"counts": count_document(b"baba")}])
        self.assertEqual(fields["byte_to_order"][97:99], [0, 1])
        self.assertEqual(fields["byte_to_order"][99], 2)

    def test_quantization_boundaries_and_frequency_ties(self):
        # Each independent two-letter document contributes exactly one pair.
        documents = [{"counts": count_document(pair)} for pair, n in
                     ((b"aa", 95), (b"ab", 4), (b"bb", 1)) for _ in range(n)]
        fields, audit = derive(documents)
        self.assertEqual(fields["pair_categories"], [3, 2, 0, 1])
        self.assertEqual(audit, {"positive_pair_mass": 95, "letter_pair_mass": 100, "frequent_pair_mass": 100})
        fields, _ = derive([{"counts": count_document(pair)} for pair in (b"ab", b"ba")])
        self.assertEqual(fields["pair_categories"], [0, 3, 3, 0])

    def test_binary32_exact_rounding(self):
        self.assertEqual(binary32_ratio(1, 3), "3eaaaaab")
        self.assertEqual(binary32_ratio(1, 1), "3f800000")
        self.assertEqual(binary32_ratio((1 << 24) + 1, 1 << 25), "3f000000")
        self.assertEqual(binary32_ratio((1 << 24) + 3, 1 << 25), "3f000002")
        self.assertEqual(binary32_ratio(1, 1 << 149), "00000001")
        with self.assertRaises(ValueError):
            binary32_ratio(1, 1 << 150)
        for n, d in ((0, 1), (2, 1), (True, 2)):
            with self.assertRaises(ValueError):
                binary32_ratio(n, d)

    def test_recomputation_rejects_forged_tables_audit_and_dependencies(self):
        for mutate in (lambda a: a["contract"]["pair_categories"].__setitem__(0, 1),
                       lambda a: a["audit"].__setitem__("positive_pair_mass", 0),
                       lambda a: a["dependencies"].__setitem__("corpus/framework.py", "0" * 64),
                       lambda a: a["spec"].__setitem__("positive_mass_percent", 90),
                       lambda a: a["documents"][0]["counts"]["symbols"].__setitem__(0, 10)):
            artifact = copy.deepcopy(self.artifact)
            mutate(artifact)
            artifact["content_hash"] = content_hash(artifact)
            with self.assertRaises(ValueError):
                validate(artifact)

    def test_duplicate_origins_and_nontraining_audit_rejected(self):
        for mutate in (lambda a: a["documents"][1]["source"].__setitem__("origin", a["documents"][0]["source"]["origin"]),
                       lambda a: a["documents"][1]["source"].__setitem__("sha256", a["documents"][0]["source"]["sha256"]),
                       lambda a: a["documents"][0]["source"].__setitem__("split", "validation"),
                       lambda a: a["documents"][0]["source"].__setitem__("language", "de"),
                       lambda a: a.__setitem__("documents", [])):
            artifact = copy.deepcopy(self.artifact)
            mutate(artifact)
            artifact["content_hash"] = content_hash(artifact)
            with self.assertRaises(ValueError):
                validate(artifact)

    def test_missing_full_variant_rejected(self):
        manifest = generate(dict(sources=self.manifest["sources"], encodings=["cp1252"], byte_limits=[3]),
                            self.root / "corpus", self.root / "only-variants")
        with self.assertRaisesRegex(ValueError, "no full"):
            train(manifest, self.root / "only-variants", "fr")

    def test_cli_python_only_regeneration_audit(self):
        artifact = self.root / "artifact.json"
        artifact.write_bytes(canonical(self.artifact))
        manifest = self.root / "corpus" / "manifest-copy.json"
        manifest.write_text(json.dumps(self.manifest), encoding="utf-8")
        tool = Path(__file__).with_name("sequence_training.py")
        subprocess.run([sys.executable, str(tool), "validate", str(artifact), "--manifest", str(manifest)],
                       check=True, timeout=30)

    def test_document_order_and_no_evidence(self):
        documents = self.artifact["documents"]
        self.assertEqual(derive(documents), derive(list(reversed(documents))))
        for data in (b"", b"123", b"a b", b"\x81aa"):
            with self.assertRaises(ValueError):
                derive([{"counts": count_document(data)}])

    def test_letter_limit_and_reserved_order(self):
        letters = bytes(b for b, kind in enumerate(character_classes()) if kind == "letter")
        fields, _ = derive([{"counts": count_document(letters)}])
        self.assertEqual(fields["frequent_character_count"], 64)
        self.assertNotIn(250, fields["byte_to_order"])
        self.assertEqual(len(fields["pair_categories"]), 64 * 64)

    def test_corpus_bytes_are_revalidated(self):
        sample = next(s for s in self.manifest["samples"] if s["byte_limit"] is None and s["format"] == "text")
        path = self.root / "corpus" / sample["path"]
        path.write_bytes(path.read_bytes() + b"tamper")
        with self.assertRaises(ValueError):
            train(self.manifest, self.root / "corpus", "fr")

    def test_no_training_or_wrong_language_rejected(self):
        with self.assertRaisesRegex(ValueError, "no full"):
            train(self.manifest, self.root / "corpus", "de")
        manifest = copy.deepcopy(self.manifest)
        for source in manifest["sources"]:
            source["split"] = "validation"
        for sample in manifest["samples"]:
            sample["split"] = "validation"
        manifest["content_hash"] = corpus_hash(manifest)
        with self.assertRaisesRegex(ValueError, "no full"):
            train(manifest, self.root / "corpus", "fr")

    def test_runtime_revision_is_pinned(self):
        artifact = copy.deepcopy(self.artifact)
        artifact["runtime"]["python"] = "0.0.0"
        artifact["content_hash"] = content_hash(artifact)
        with self.assertRaisesRegex(ValueError, "runtime revision"):
            validate(artifact)


if __name__ == "__main__":
    unittest.main()
