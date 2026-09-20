# SPDX-License-Identifier: MIT
import copy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from model import canonical, emit_cpp, model_hash, score, train, validate_model, write_idempotent
from framework import digest, generate


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        sources = []
        for id, text, split in (("train1", "café café", "training"), ("train2", "thé", "training"),
                                ("heldout", "thé café!", "validation")):
            data = text.encode("utf-8")
            (self.root / f"{id}.txt").write_bytes(data)
            sources.append(dict(id=id, path=f"{id}.txt", language="fr", license="MIT",
                license_reference="corpus/LICENSES/MIT.txt", revision="fixture-v1", origin=f"synthetic:{id}",
                kind="synthetic", sha256=digest(data), split=split))
        self.manifest = generate(dict(sources=sources, encodings=["cp1252"], byte_limits=[None, 3]),
                                 self.root, self.root / "corpus")
        self.model = train(self.manifest, self.root / "corpus", "fr")

    def test_determinism_separate_from_idempotence(self):
        other = train(self.manifest, self.root / "corpus", "fr")
        self.assertEqual(canonical(self.model), canonical(other))
        self.assertEqual(emit_cpp(self.model), emit_cpp(other))

    def test_idempotent_artifact_no_rewrite(self):
        path = self.root / "model.json"
        data = canonical(self.model)
        write_idempotent(path, data)
        before = path.stat().st_mtime_ns
        write_idempotent(path, data)
        self.assertEqual(before, path.stat().st_mtime_ns)
        with self.assertRaises(ValueError):
            write_idempotent(path, b"different")

    def test_training_only_no_cross_document_pairs(self):
        self.assertEqual(self.model["byte_count"], len("café caféthé"))
        self.assertEqual(self.model["pair_count"], self.model["byte_count"] - 2)
        self.assertTrue(all(p["source"]["split"] == "training" for p in self.model["sources"]))
        self.assertEqual(self.model["generated_model_license"], "UNDETERMINED")

    def test_heldout_report_not_accuracy(self):
        report = score(self.model, self.manifest, self.root / "corpus", "validation")
        self.assertTrue(report["synthetic_only"])
        self.assertIn("NOT encoding accuracy", report["metric"])
        self.assertEqual(len(report["samples"]), 1)
        self.assertGreater(report["samples"][0]["bits_per_pair"], 0)
        with self.assertRaises(ValueError):
            score(self.model, self.manifest, self.root / "corpus", "training")

    def test_heldout_origin_leakage_across_manifests(self):
        model = copy.deepcopy(self.model)
        model["sources"][0]["source"]["origin"] = "synthetic:heldout"
        model["content_hash"] = model_hash(model)
        with self.assertRaisesRegex(ValueError, "leakage"):
            score(model, self.manifest, self.root / "corpus", "validation")

    def test_invalid_tables_rejected(self):
        mutations = [lambda m: m["symbol_counts"].pop(),
                     lambda m: m["symbol_counts"].__setitem__(0, -1),
                     lambda m: m["symbol_counts"].__setitem__(0, 2**64),
                     lambda m: m["bigrams"].reverse(),
                     lambda m: m["bigrams"].append(m["bigrams"][-1]),
                     lambda m: m["bigrams"][0].__setitem__(2, 2**63),
                     lambda m: m.__setitem__("encoding", "utf-8")]
        for mutate in mutations:
            model = copy.deepcopy(self.model)
            mutate(model)
            model["content_hash"] = model_hash(model)
            with self.assertRaises(ValueError):
                validate_model(model)

    def test_missing_language_is_not_silent(self):
        with self.assertRaises(ValueError):
            train(self.manifest, self.root / "corpus", "ja")

    @unittest.skipUnless(shutil.which("g++"), "g++ unavailable")
    def test_emitted_header_compiles_and_values_match(self):
        header = self.root / "model.hpp"
        header.write_bytes(emit_cpp(self.model))
        source = self.root / "check.cpp"
        source.write_text('#include "model.hpp"\n'
            'int main() { return uchardet_model_pilot::symbols[233] == 3 ? 0 : 1; }\n',
            encoding="utf-8")
        executable = self.root / "check-model.exe"
        subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", str(source),
                        "-o", str(executable)], check=True, timeout=60)
        subprocess.run([str(executable)], check=True, timeout=30)


if __name__ == "__main__":
    unittest.main()
