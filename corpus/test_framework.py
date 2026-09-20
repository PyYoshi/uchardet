# SPDX-License-Identifier: MIT
"""Synthetic fixtures exercise infrastructure, not natural-language accuracy."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from framework import audit_manifests, audit_splits, content_hash, digest, encode_variant, generate, safe_path, validate


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

    def test_invalid_split_preflight_leaves_no_output(self):
        config = copy.deepcopy(self.config)
        config["sources"].append(dict(config["sources"][0], id="renamed", split="training"))
        with self.assertRaisesRegex(ValueError, "split leakage"):
            self.generate(config)
        self.assertFalse((self.root / "out").exists())
        self.generate()

    def test_duplicate_id_preflight_and_artifact_budget(self):
        config = copy.deepcopy(self.config)
        config["sources"].append(config["sources"][0])
        with self.assertRaisesRegex(ValueError, "duplicate source"):
            self.generate(config)
        self.assertFalse((self.root / "out").exists())
        with patch("framework.MAX_ARTIFACT_BYTES", len(self.raw) + 1):
            with self.assertRaisesRegex(ValueError, "budget"):
                self.generate()
        self.assertFalse((self.root / "out").exists())

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
        manifest = json.loads((self.root / "out/manifest.json").read_text(encoding="utf-8"))
        target = self.root / "out" / manifest["samples"][0]["path"]
        target.write_bytes(b"tampered")
        self.assert_invalid(manifest)

    def test_no_overwrite(self):
        self.generate()
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.generate()

    def test_continue_accounts_for_every_variant_without_detector_metrics(self):
        self.config["encodings"].append("ascii")
        with self.assertRaises(UnicodeEncodeError):
            self.generate()
        self.assertFalse((self.root / "out").exists())
        manifest = generate(self.config, self.root, self.root / "out", failure_policy="record-and-continue")
        report = manifest["generation_report"]
        self.assertEqual(report["counts"], {"attempted": 72, "successful": 48, "skipped": 24})
        skips = [record for record in report["attempts"] if record["status"] == "skipped"]
        self.assertEqual({record["reason"] for record in skips}, {"unencodable"})
        self.assertEqual({record["encoding"] for record in skips}, {"ascii"})
        self.assertEqual(len({(r["source_id"], r["encoding"], r["format"], r["byte_limit"], r["boundary"])
                              for r in report["attempts"]}), 72)
        self.assertNotIn("accuracy", report)
        validate(manifest, self.root / "out")
        duplicate = generate(self.config, self.root, self.root / "two", failure_policy="record-and-continue")
        self.assertEqual(manifest, duplicate)

    def test_continue_records_non_roundtrip_even_when_prefix_would_fit(self):
        raw = "abc\u00a5".encode("utf-8")
        (self.root / "input.txt").write_bytes(raw)
        self.config["sources"][0]["sha256"] = digest(raw)
        self.config.update(encodings=["shift_jis"], formats=["text"], byte_limits=[1])
        manifest = generate(self.config, self.root, self.root / "out", failure_policy="record-and-continue")
        self.assertEqual(manifest["samples"], [])
        self.assertEqual(manifest["generation_report"]["counts"],
                         {"attempted": 2, "successful": 0, "skipped": 2})
        self.assertEqual({r["reason"] for r in manifest["generation_report"]["attempts"]}, {"non-roundtrip"})

    def test_continue_does_not_mask_config_source_or_io_failure(self):
        self.config["encodings"] = ["ascii"]
        for key, bad in (("byte_limits", [True]), ("byte_limits", [0]),
                         ("boundaries", ["wrong"]), ("formats", ["wrong"]),
                         ("encodings", ["does-not-exist"]), ("encodings", ["base64_codec"]),
                         ("encodings", ["utf8", "utf-8"]), ("formats", []),
                         ("byte_limits", "wrong")):
            config = copy.deepcopy(self.config)
            config[key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaises((ValueError, LookupError)):
                generate(config, self.root, self.root / "out", failure_policy="record-and-continue")
            self.assertFalse((self.root / "out").exists())
        self.config["sources"][0]["path"] = "missing.txt"
        with self.assertRaises(FileNotFoundError):
            generate(self.config, self.root, self.root / "out", failure_policy="record-and-continue")
        self.config["sources"][0]["path"] = "input.txt"
        self.config["sources"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash"):
            generate(self.config, self.root, self.root / "out", failure_policy="record-and-continue")

    def test_report_tampering_is_rejected_with_recomputed_manifest_hash(self):
        self.config["encodings"].append("ascii")
        manifest = generate(self.config, self.root, self.root / "out", failure_policy="record-and-continue")
        for mutation in ("count", "omission", "reason", "dimension", "status", "sample"):
            changed = copy.deepcopy(manifest)
            report = changed["generation_report"]
            if mutation == "count":
                report["counts"]["skipped"] = 0
            elif mutation == "omission":
                report["attempts"].pop()
            elif mutation == "reason":
                report["attempts"][-1]["reason"] = "non-roundtrip"
            elif mutation == "dimension":
                report["dimensions"]["byte_limits"].append(123)
            elif mutation == "status":
                report["attempts"][0] = dict(report["attempts"][-1])
            else:
                changed["samples"].pop()
            with self.subTest(mutation=mutation):
                self.assert_invalid(changed)

    def test_ground_truth_is_provenance_not_unique_encoding_claim(self):
        self.config.update(encodings=["utf-8"], formats=["text"], byte_limits=[1, None])
        manifest = self.generate()
        for sample in manifest["samples"]:
            expected = "byte-truncated" if sample["boundary"] == "truncated" and sample["byte_limit"] == 1 else "strict-roundtrip"
            self.assertEqual(sample["ground_truth"],
                             {"provenance": "strict-source-reencoding", "certainty": expected})
        manifest["samples"][0]["ground_truth"]["certainty"] = "byte-truncated"
        self.assert_invalid(manifest)

    def test_legacy_manifest_without_report_or_ground_truth_remains_readable(self):
        manifest = self.generate()
        del manifest["generation_report"]
        for sample in manifest["samples"]:
            del sample["ground_truth"]
        manifest["content_hash"] = content_hash(manifest)
        validate(manifest, self.root / "out")

    def test_cross_manifest_split_audit_only_reads_metadata(self):
        first = self.generate(name="one")
        second = self.generate(name="two")
        # Paths need not exist: the audit reads no source bytes or held-out samples.
        for manifest in (first, second):
            manifest["sources"][0]["path"] = "not-present.txt"
            manifest["content_hash"] = content_hash(manifest)
        self.assertEqual(audit_splits([first, second]),
                         {"manifests": 2, "source_records": 2, "split_leakage": False})
        path = self.root / "metadata.json"
        path.write_text(json.dumps(first), encoding="utf-8")
        self.assertEqual(audit_manifests([path])["source_records"], 1)
        for shared in ("sha256", "origin"):
            changed = copy.deepcopy(second)
            source = changed["sources"][0]
            source.update(id="independent-renamed", split="independent")
            if shared == "sha256":
                source["origin"] = "different:origin"
            else:
                source["sha256"] = "f" * 64
            changed["content_hash"] = content_hash(changed)
            with self.subTest(shared=shared), self.assertRaisesRegex(ValueError, "cross-manifest"):
                audit_splits([first, changed])

    def test_cli_continue_validate_and_metadata_audit(self):
        self.config["encodings"].append("ascii")
        config = self.root / "config.json"
        config.write_text(json.dumps(self.config), encoding="utf-8")
        command = [sys.executable, str(Path(__file__).with_name("framework.py"))]
        subprocess.run(command + ["generate", str(config), str(self.root / "out"),
                                  "--failure-policy", "record-and-continue"], check=True, capture_output=True)
        manifest = self.root / "out/manifest.json"
        subprocess.run(command + ["validate", str(manifest)], check=True, capture_output=True)
        result = subprocess.run(command + ["audit-splits", str(manifest)],
                                check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout),
                         {"manifests": 1, "source_records": 1, "split_leakage": False})
        changed = json.loads(manifest.read_text(encoding="utf-8"))
        changed["sources"][0]["origin"] = "changed-without-hash-update"
        manifest.write_text(json.dumps(changed), encoding="utf-8")
        result = subprocess.run(command + ["audit-splits", str(manifest)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
