# SPDX-License-Identifier: MIT
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from model import canonical, digest, write_idempotent
from framework import generate
from sequence_training import character_classes, train
from sequence_evaluation import SIZE_BOUNDS, counts, evaluate, rates, size_strata, summarize


class SequenceEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.training_manifest, self.training_root = self.corpus("train", [("train", "abba", "training", "synthetic:train", "fr")])
        self.training = train(self.training_manifest, self.training_root, "fr")
        self.manifest, self.corpus_root = self.corpus("evaluation", [
            ("validation", "ac aa", "validation", "synthetic:validation", "fr"),
            ("tuning", "bb ab", "tuning", "synthetic:tuning", "fr"),
            ("independent", "sealed holdout", "independent", "synthetic:independent", "fr")])

    def corpus(self, name, documents, limits=None):
        root = self.root / name
        root.mkdir()
        sources = []
        for id, text, split, origin, language in documents:
            data = text.encode()
            (root / f"{id}.txt").write_bytes(data)
            sources.append(dict(id=id, path=f"{id}.txt", language=language, license="MIT",
                license_reference="corpus/LICENSES/MIT.txt", revision="synthetic-v1", origin=origin,
                kind="synthetic", sha256=digest(data), split=split))
        manifest = generate(dict(sources=sources, encodings=["cp1252"], byte_limits=limits or [None, 3],
                                 formats=["text", "html-clean"]), root, root / "corpus")
        return manifest, root / "corpus"

    def test_exact_coverage_denominators(self):
        report = evaluate(self.training, [(self.manifest, self.corpus_root)], "validation")
        self.assertEqual(report["aggregate_counts"], dict(bytes=5, letters=4, frequent_letters=3,
            known_rare_letters=0, unknown_letters=1, adjacent_letter_pairs=2, matrix_pairs=1,
            outside_matrix_pairs=1, unseen_matrix_pairs=1, category_mass=[1, 0, 0, 0]))
        self.assertEqual(report["aggregate_rates"]["unseen_matrix_pair_rate"], {"numerator": 1, "denominator": 1})
        self.assertEqual(report["aggregate_rates"]["frequent_letter_coverage"], {"numerator": 3, "denominator": 4})
        self.assertEqual(report["source_count"], 1)
        self.assertTrue(report["synthetic_only"])
        self.assertEqual(report["deployment_status"], "NOT_ENGINE_CALIBRATED")
        self.assertNotIn("confidence", report["aggregate_counts"])
        self.assertEqual(report["sources"][0]["source"]["id"], "validation")
        self.assertEqual(report["schema"], "sequence-coverage-evaluation-v2")
        self.assertEqual(report["macro_rates"]["frequent_letter_coverage"],
                         {"defined_documents": 1, "undefined_documents": 0,
                          "mean": {"numerator": 3, "denominator": 4}})

    def observed(self, data):
        return {"counts": counts(data, self.training["contract"], {97, 98})}

    def test_macro_is_not_micro_and_excludes_only_undefined(self):
        documents = [self.observed(data) for data in (b"a", b"ccccccccc", b"123")]
        result = summarize(documents)
        self.assertEqual(result["aggregate_rates"]["frequent_letter_coverage"],
                         {"numerator": 1, "denominator": 10})
        self.assertEqual(result["macro_rates"]["frequent_letter_coverage"],
                         {"defined_documents": 2, "undefined_documents": 1,
                          "mean": {"numerator": 1, "denominator": 2}})
        # Zero coverage is defined; single-letter documents have no pair rate.
        self.assertEqual(result["macro_rates"]["matrix_pair_coverage"],
                         {"defined_documents": 1, "undefined_documents": 2,
                          "mean": {"numerator": 0, "denominator": 1}})

    def test_exact_macro_fraction(self):
        result = summarize([self.observed(b"acc"), self.observed(b"ac")])
        self.assertEqual(result["macro_rates"]["frequent_letter_coverage"]["mean"],
                         {"numerator": 5, "denominator": 12})

    def test_empty_summary_is_explicit_not_zero_accuracy(self):
        result = summarize([])
        self.assertEqual(result["source_count"], 0)
        self.assertTrue(all(value is None for value in result["aggregate_rates"].values()))
        for value in result["macro_rates"].values():
            self.assertEqual(value, {"defined_documents": 0, "undefined_documents": 0,
                                     "mean": None})

    def test_size_boundaries_partition_counts_without_new_pairs(self):
        lengths = [0, *(n - 1 for n in SIZE_BOUNDS), *SIZE_BOUNDS, SIZE_BOUNDS[-1] + 1]
        documents = [self.observed(b"a" * n) for n in lengths]
        strata = size_strata(documents)
        self.assertEqual(sum(row["source_count"] for row in strata), len(documents))
        for row in strata:
            lower, upper = row["minimum_bytes_inclusive"], row["maximum_bytes_exclusive"]
            self.assertEqual(row["source_count"],
                             sum(n >= lower and (upper is None or n < upper) for n in lengths))
        total = summarize(documents)["aggregate_counts"]
        for key, value in total.items():
            if key == "category_mass":
                self.assertEqual([sum(row["aggregate_counts"][key][i] for row in strata)
                                  for i in range(4)], value)
            else:
                self.assertEqual(sum(row["aggregate_counts"][key] for row in strata), value)
        self.assertEqual(size_strata(documents[::-1]), strata)

    def test_independent_and_training_are_rejected(self):
        for split in ("independent", "training"):
            with self.assertRaisesRegex(ValueError, "only tuning/validation"):
                evaluate(self.training, [(self.manifest, self.corpus_root)], split)

    def test_tuning_uses_fixed_tables(self):
        before = canonical(self.training)
        report = evaluate(self.training, [(self.manifest, self.corpus_root)], "tuning")
        self.assertEqual(report["aggregate_counts"]["category_mass"], [0, 0, 0, 2])
        self.assertEqual(canonical(self.training), before)

    def test_training_hash_and_origin_leakage_even_unselected_language(self):
        for index, (text, origin) in enumerate((("abba", "synthetic:other"), ("different", "synthetic:train"))):
            manifest, root = self.corpus(f"leak-{index}", [("leak", text, "validation", origin, "de")])
            with self.assertRaisesRegex(ValueError, "leakage"):
                evaluate(self.training, [(self.manifest, self.corpus_root), (manifest, root)], "validation")

    def test_cross_manifest_split_leakage(self):
        manifest, root = self.corpus("split-leak", [("other", "changed", "tuning", "synthetic:validation", "fr")])
        with self.assertRaisesRegex(ValueError, "leakage"):
            evaluate(self.training, [(self.manifest, self.corpus_root), (manifest, root)], "validation")

    def test_duplicate_selected_origins_and_hashes(self):
        for index, (text, origin) in enumerate((("ac aa", "synthetic:other"), ("different", "synthetic:validation"))):
            manifest, root = self.corpus(f"duplicate-{index}", [("other", text, "validation", origin, "fr")])
            with self.assertRaisesRegex(ValueError, "duplicate selected"):
                evaluate(self.training, [(self.manifest, self.corpus_root), (manifest, root)], "validation")

    def test_no_cross_document_pairs_and_zero_denominator(self):
        manifest, root = self.corpus("short", [("a", "a", "validation", "synthetic:a", "fr"),
                                                ("b", "b", "validation", "synthetic:b", "fr")])
        report = evaluate(self.training, [(manifest, root)], "validation")
        self.assertEqual(report["aggregate_counts"]["adjacent_letter_pairs"], 0)
        self.assertIsNone(report["aggregate_rates"]["unseen_matrix_pair_rate"])
        self.assertIsNone(report["aggregate_rates"]["matrix_pair_coverage"])
        empty = counts(b"", self.training["contract"], {97, 98})
        self.assertTrue(all(value is None for value in rates(empty).values()))

    def test_known_rare_letter_is_not_unknown(self):
        alphabet = bytes(i for i, kind in enumerate(character_classes()) if kind == "letter").decode("cp1252")
        manifest, root = self.corpus("alphabet", [("alphabet", alphabet, "training", "synthetic:alphabet", "fr")])
        trained = train(manifest, root, "fr")
        rare = next(i for i in alphabet.encode("cp1252") if trained["contract"]["byte_to_order"][i] == 64)
        result = counts(bytes([rare]), trained["contract"], set(alphabet.encode("cp1252")))
        self.assertEqual(result["known_rare_letters"], 1)
        self.assertEqual(result["unknown_letters"], 0)

    def test_determinism_manifest_order_and_idempotence(self):
        other, root = self.corpus("other", [("other", "ba ba", "validation", "synthetic:other", "fr")])
        inputs = [(self.manifest, self.corpus_root), (other, root)]
        report = evaluate(self.training, inputs, "validation")
        self.assertEqual(canonical(report), canonical(evaluate(self.training, inputs[::-1], "validation")))
        path = self.root / "report.json"
        write_idempotent(path, canonical(report))
        timestamp = path.stat().st_mtime_ns
        write_idempotent(path, canonical(report))
        self.assertEqual(path.stat().st_mtime_ns, timestamp)
        self.assertIn("models/experimental/sequence_evaluation.py", report["evaluator_dependencies"])

    def test_model_and_actual_sample_revalidated(self):
        broken = copy.deepcopy(self.training)
        broken["contract"]["pair_categories"][0] = 3
        with self.assertRaises(ValueError):
            evaluate(broken, [(self.manifest, self.corpus_root)], "validation")
        sample = self.manifest["samples"][0]
        path = self.corpus_root / sample["path"]
        path.write_bytes(path.read_bytes() + b"tampered")
        with self.assertRaises(ValueError):
            evaluate(self.training, [(self.manifest, self.corpus_root)], "validation")

    def test_missing_full_variant(self):
        manifest, root = self.corpus("variant", [("short", "ab ab", "validation", "synthetic:short", "fr")], [3])
        with self.assertRaisesRegex(ValueError, "no full complete"):
            evaluate(self.training, [(manifest, root)], "validation")

    def test_training_manifest_can_be_audited_but_not_scored(self):
        report = evaluate(self.training, [(self.training_manifest, self.training_root),
                                          (self.manifest, self.corpus_root)], "validation")
        self.assertEqual(report["source_count"], 1)
        self.assertEqual(len(report["audited_manifests"]), 2)
        with self.assertRaisesRegex(ValueError, "duplicate evaluation manifest"):
            evaluate(self.training, [(self.manifest, self.corpus_root)] * 2, "validation")

    def test_cli_python_only(self):
        training = self.root / "training.json"
        training.write_bytes(canonical(self.training))
        manifest = self.corpus_root / "manifest-copy.json"
        manifest.write_text(json.dumps(self.manifest), encoding="utf-8")
        output = self.root / "diagnostics.json"
        subprocess.run([sys.executable, str(Path(__file__).with_name("sequence_evaluation.py")),
                        str(training), "validation", str(output), str(manifest)], check=True, timeout=30)
        self.assertEqual(json.loads(output.read_text())["source_count"], 1)


if __name__ == "__main__":
    unittest.main()
