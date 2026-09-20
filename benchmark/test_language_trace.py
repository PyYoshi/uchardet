# SPDX-License-Identifier: MIT
"""Read-only language snapshots on the existing tiny trace fixtures."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get("UCHARDET_TRACE"), "set UCHARDET_TRACE")
class LanguageTraceTests(unittest.TestCase):
    text = "日本語の文章です。".encode() * 5

    def trace(self, data, chunk, tool=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(data)
            result = subprocess.run(
                [tool or os.environ["UCHARDET_TRACE"], str(chunk), str(path)],
                check=True, capture_output=True, text=True, timeout=30,
            )
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_unallocated_is_null(self):
        for data in (b"", b"plain text\n"):
            for record in self.trace(data, 7):
                if record["event"] != "raw_report":
                    self.assertIsNone(record["language_detectors"])

    def test_initialized_counters_and_static_model_labels(self):
        observed_characters = False
        observed_model_free = False
        observed_model = False
        observed_uncategorized = False
        for record in self.trace(self.text, 7):
            if record["event"] == "raw_report":
                continue
            slots = record["language_detectors"]
            if slots is None:
                continue
            indices = [(s["prober_index"], s["language_index"]) for s in slots]
            self.assertEqual(indices, sorted(set(indices)))
            for slot in slots:
                self.assertIn(slot["state"], ("detecting", "found", "unlikely"))
                self.assertEqual(slot["state_reason"], "unknown")
                self.assertGreaterEqual(slot["total_characters"], 0)
                self.assertGreaterEqual(slot["total_sequences"], 0)
                self.assertEqual(len(slot["sequence_categories"]), 4)
                self.assertTrue(all(n >= 0 for n in slot["sequence_categories"]))
                # Model-external pairs add to the denominator, not the four buckets.
                categorized = sum(slot["sequence_categories"])
                self.assertLessEqual(categorized, slot["total_sequences"])
                observed_uncategorized |= categorized < slot["total_sequences"]
                observed_characters |= slot["total_characters"] > 0
                observed_model_free |= slot["model_language"] is None
                observed_model |= slot["model_language"] == "fr"
        self.assertTrue(observed_characters)
        self.assertTrue(observed_model_free)
        self.assertTrue(observed_model)
        self.assertTrue(observed_uncategorized)

    def test_deterministic_without_input_body(self):
        first = self.trace(self.text, 1)
        self.assertEqual(first, self.trace(self.text, 1))
        self.assertNotIn("日本語", json.dumps(first, ensure_ascii=False))
        self.assertNotIn(self.text.hex(), json.dumps(first))

    @unittest.skipUnless(os.environ.get("UCHARDET_LANGUAGE_TRACE_BASELINE"),
                         "set trace baseline with children but without language snapshots")
    def test_prior_snapshots_and_reports_unchanged(self):
        for data in (b"", b"plain text\n", self.text):
            for chunk in (0, 1, 7, 64, 1024):
                current = self.trace(data, chunk)
                for record in current:
                    record.pop("language_detectors", None)
                baseline = self.trace(data, chunk, os.environ["UCHARDET_LANGUAGE_TRACE_BASELINE"])
                self.assertEqual(current, baseline)


if __name__ == "__main__":
    unittest.main()
