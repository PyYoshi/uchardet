# SPDX-License-Identifier: MIT
"""Synthetic rows and mocked HTTP only; no real downloads or detector execution."""

import bz2
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tatoeba

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from framework import generate


class TatoebaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.payload = (
            "20\tfra\tCafé.\t2019-01-12 19:39:42\n"
            "3\tfra\tEmoji 😀 et \\n littéral.\tmetadata-not-interpreted\n"
        ).encode("utf-8")
        self.archive = self.root / "download.bz2"
        self.archive.write_bytes(bz2.compress(self.payload))
        self.snapshot = self.root / "snapshot"

    def imported(self):
        return tatoeba.import_cache(
            "fra",
            self.archive,
            self.snapshot,
            captured_at="2026-09-20T13:18:56Z",
            expected_sha256=tatoeba.digest(self.archive.read_bytes()),
        )

    def test_import_offline_validation_and_provenance(self):
        with patch.object(
            tatoeba.urllib.request, "build_opener", side_effect=AssertionError("network")
        ):
            snapshot = self.imported()
            verified, rows = tatoeba.validate(self.snapshot)
        self.assertEqual(snapshot, verified)
        self.assertEqual(snapshot["capture_method"], "operator-import")
        self.assertEqual(snapshot["uncompressed_sha256"], tatoeba.digest(self.payload))
        self.assertEqual(snapshot["compressed_bytes"], self.archive.stat().st_size)
        self.assertEqual(snapshot["license"], "CC0-1.0")
        self.assertEqual(rows[1]["export_metadata_raw"], "metadata-not-interpreted")
        self.assertIn("\\n", rows[1]["text"])
        self.assertNotIn("\n", rows[1]["text"])

    def test_ingest_selection_split_and_unrepresentable_source_retained(self):
        self.imported()
        output = self.root / "ingested"
        with patch.object(
            tatoeba.urllib.request, "build_opener", side_effect=AssertionError("network")
        ):
            report = tatoeba.ingest(self.snapshot, output, limit=1)
        self.assertEqual(report["selected_ids"], [3])
        self.assertEqual(report["available_sentences"], 2)
        self.assertFalse(report["legacy_representability_filter"])
        config = json.loads((output / "config.json").read_text(encoding="utf-8"))
        source = config["sources"][0]
        self.assertEqual(source["split"], "validation")
        self.assertEqual(source["origin"], "tatoeba:cc0-pilot")
        self.assertEqual(source["tatoeba_sentence_id"], 3)
        self.assertEqual(source["language"], "fr")
        self.assertEqual(source["export_metadata_raw"], "metadata-not-interpreted")
        self.assertIn("😀", (output / source["path"]).read_text(encoding="utf-8"))
        generated = generate(
            config, output, self.root / "generated", failure_policy="record-and-continue"
        )
        self.assertEqual(
            generated["generation_report"]["counts"],
            {"attempted": 6, "successful": 3, "skipped": 3},
        )

    def test_russian_config_uses_same_origin_and_cp1251(self):
        self.archive.write_bytes(bz2.compress("2\trus\tПример.\tmetadata\n".encode()))
        tatoeba.import_cache(
            "rus",
            self.archive,
            self.snapshot,
            captured_at="2026-09-20T00:00:00+00:00",
            expected_sha256=tatoeba.digest(self.archive.read_bytes()),
        )
        output = self.root / "ru"
        tatoeba.ingest(self.snapshot, output)
        config = json.loads((output / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["encodings"], ["utf-8", "cp1251"])
        self.assertEqual(config["sources"][0]["origin"], tatoeba.ORIGIN)
        self.assertEqual(config["sources"][0]["split"], "validation")

    def test_ingest_deterministic_and_never_overwrites(self):
        self.imported()
        for name in ("one", "two"):
            tatoeba.ingest(self.snapshot, self.root / name)
        for path in (self.root / "one").rglob("*"):
            if path.is_file():
                other = self.root / "two" / path.relative_to(self.root / "one")
                self.assertEqual(path.read_bytes(), other.read_bytes())
        with self.assertRaises(ValueError):
            tatoeba.ingest(self.snapshot, self.root / "one")
        with self.assertRaises(ValueError):
            self.imported()

    def test_capture_mocked_official_url_and_hashes(self):
        class Response(io.BytesIO):
            status = 200
            headers = {"Last-Modified": "Sat, 19 Sep 2026 06:31:34 GMT"}

            def geturl(self):
                return tatoeba.official_url("fra")

        response = Response(self.archive.read_bytes())
        with patch.object(tatoeba.urllib.request, "build_opener") as factory:
            factory.return_value.open.return_value = response
            snapshot = tatoeba.capture("fra", self.snapshot)
            request = factory.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, tatoeba.official_url("fra"))
        self.assertEqual(snapshot["capture_method"], "direct-https")
        self.assertEqual(snapshot["http_last_modified_raw"], Response.headers["Last-Modified"])
        self.assertEqual(tatoeba.validate(self.snapshot)[0], snapshot)
        with patch.object(
            tatoeba.urllib.request, "build_opener", side_effect=AssertionError("network")
        ):
            with self.assertRaises(ValueError):
                tatoeba.capture("fra", self.snapshot)
            with self.assertRaises(ValueError):
                tatoeba.capture("https://example.com/other.bz2", self.root / "other")

    def test_redirect_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "redirect"):
            tatoeba.NoRedirect().redirect_request(
                None, None, 302, None, None, tatoeba.official_url("fra")
            )

    def test_format_is_strict_and_metadata_is_uninterpreted(self):
        for payload in (
            b"1\tfra\ttext\n",
            b"1\tfra\ttext\tx\textra\n",
            b"1\trus\ttext\tx\n",
            b"x\tfra\ttext\tx\n",
            b"1\tfra\ttext\tx\r\n",
            b"",
            b"1\tfra\t\tx\n",
            b"1\tfra\ttext\tx\n1\tfra\tother\ty\n",
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                tatoeba.parse_sentences(payload, "fra")
        with self.assertRaises(UnicodeDecodeError):
            tatoeba.parse_sentences(b"1\tfra\t\xff\tx\n", "fra")

    def test_import_hash_and_capture_time_rejected(self):
        for sha, timestamp in (
            ("0" * 64, "2026-09-20T00:00:00Z"),
            ("bad", "2026-09-20T00:00:00Z"),
            (tatoeba.digest(self.archive.read_bytes()), "2026-09-20T00:00:00"),
        ):
            with self.subTest(sha=sha, timestamp=timestamp), self.assertRaises(ValueError):
                tatoeba.import_cache(
                    "fra", self.archive, self.snapshot, captured_at=timestamp, expected_sha256=sha
                )
            self.assertFalse(self.snapshot.exists())

    def test_budget_and_archive_completeness(self):
        compressed = self.archive.read_bytes()
        with patch.object(tatoeba, "MAX_COMPRESSED_BYTES", len(compressed) - 1):
            with self.assertRaisesRegex(ValueError, "2 MiB"):
                tatoeba.decompress(compressed)
        with patch.object(tatoeba, "MAX_UNCOMPRESSED_BYTES", len(self.payload) - 1):
            with self.assertRaisesRegex(ValueError, "20 MiB"):
                tatoeba.decompress(compressed)
        for data in (compressed[:-1], compressed + b"trailing", compressed + compressed):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                tatoeba.decompress(data)

    def test_snapshot_tamper_and_limit_rejected(self):
        self.imported()
        for limit in (0, True, 2001, "200"):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                tatoeba.ingest(self.snapshot, self.root / "out", limit=limit)
        meta_path = self.snapshot / "snapshot.json"
        original = json.loads(meta_path.read_bytes())
        for key, value in (
            ("download_url", "https://example.com/export"),
            ("license", "CC-BY-2.0"),
            ("sentence_count", 999),
            ("uncompressed_sha256", "0" * 64),
        ):
            meta_path.write_bytes(tatoeba.serialized(dict(original, **{key: value})))
            with self.subTest(key=key), self.assertRaises(ValueError):
                tatoeba.validate(self.snapshot)
        meta_path.write_bytes(tatoeba.serialized(original))
        (self.snapshot / "sentences.tsv").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            tatoeba.validate(self.snapshot)

    def test_offline_cli_routes_and_no_split_override(self):
        commands = [
            [
                "import-cache",
                "fra",
                str(self.archive),
                str(self.snapshot),
                "--captured-at",
                "2026-09-20T00:00:00Z",
                "--sha256",
                tatoeba.digest(self.archive.read_bytes()),
            ],
            ["validate", str(self.snapshot)],
            ["ingest", str(self.snapshot), str(self.root / "out"), "--limit", "1"],
        ]
        with patch.object(
            tatoeba.urllib.request, "build_opener", side_effect=AssertionError("network")
        ):
            for args in commands:
                with (
                    patch.object(sys, "argv", ["tatoeba"] + args),
                    patch("sys.stdout", new_callable=io.StringIO) as stream,
                ):
                    tatoeba.main()
                    self.assertIsInstance(json.loads(stream.getvalue()), dict)
        args = [
            "tatoeba",
            "ingest",
            str(self.snapshot),
            str(self.root / "other"),
            "--split",
            "training",
        ]
        with patch.object(sys, "argv", args), patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as error:
                tatoeba.main()
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
