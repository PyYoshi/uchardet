# SPDX-License-Identifier: MIT
"""Observe the SBCS choice without triggering an extra score/name query."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get("UCHARDET_TRACE"), "set UCHARDET_TRACE")
class SelectionTraceTests(unittest.TestCase):
    def trace(self, data, chunk, tool=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(data)
            result = subprocess.run(
                [tool or os.environ["UCHARDET_TRACE"], str(chunk), str(path)],
                check=True, capture_output=True, text=True, timeout=10,
            )
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_cache_and_active_count_match_children(self):
        for data in (b"", b"plain ASCII", "café et thé".encode("cp1252"),
                     "日本語の文章です。".encode() * 5):
            for chunk in (0, 1, 7, 64, 1024):
                for record in self.trace(data, chunk):
                    if record["event"] == "raw_report":
                        continue
                    choice = record["singlebyte_selection"]
                    children = record["children"]["singlebyte_group"]
                    if children is None:
                        self.assertIsNone(choice)
                        continue
                    self.assertEqual(choice["active_count"], sum(
                        child["current"]["active"] for child in children))
                    index = choice["cached_best_index"]
                    if index is not None:
                        self.assertGreaterEqual(index, 0)
                        self.assertLess(index, len(children))
                        self.assertTrue(children[index]["current"]["present"])
                    state = record["probers"]["singlebyte_group"]
                    expected = {"found": "found_shortcut", "rejected": "all_rejected"}
                    self.assertEqual(choice["selection_path"], expected.get(state, "unknown"))

    def test_final_choice_identifies_reported_statistical_model(self):
        records = self.trace("café et thé".encode("cp1252"), 0)
        final = records[-1]
        self.assertEqual(final["event"], "after_end")
        index = final["singlebyte_selection"]["cached_best_index"]
        self.assertIsNotNone(index)
        models = final["prober_evidence"]["singlebyte_models"]
        selected = next(model for model in models if model["prober_index"] == index)
        reported = {(r["encoding"], r["language"]) for r in records
                    if r["event"] == "raw_report"}
        self.assertIn((selected["model_encoding"], selected["model_language"]), reported)

    @unittest.skipUnless(os.environ.get("UCHARDET_SELECTION_TRACE_BASELINE"),
                         "set selection trace baseline")
    def test_previous_observations_unchanged(self):
        for data in (b"", b"plain ASCII", "café et thé".encode("cp1252"),
                     "日本語の文章です。".encode() * 5):
            for chunk in (0, 1, 7, 64, 1024):
                current = self.trace(data, chunk)
                for record in current:
                    record.pop("singlebyte_selection", None)
                self.assertEqual(current, self.trace(
                    data, chunk, os.environ["UCHARDET_SELECTION_TRACE_BASELINE"]))


if __name__ == "__main__":
    unittest.main()
