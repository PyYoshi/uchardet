# SPDX-License-Identifier: MIT
# Copyright (c) 2026 cChardet contributors
"""Bounded observation tests; no malformed-input or crash exploration."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get("UCHARDET_TRACE"), "set UCHARDET_TRACE")
class NestedTraceTests(unittest.TestCase):
    # Reuse the existing small trace determinism fixture (135 bytes).
    text = "日本語の文章です。".encode() * 5

    def trace(self, data, chunk, tool=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(data)
            result = subprocess.run([tool or os.environ["UCHARDET_TRACE"], str(chunk), str(path)],
                                    check=True, capture_output=True, text=True, timeout=30)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_unallocated_groups_are_null(self):
        for data in (b"", b"plain text\n"):
            for record in self.trace(data, 7):
                if record["event"] != "raw_report":
                    self.assertEqual(record["children"], {"multibyte_group": None, "singlebyte_group": None})

    def test_child_indices_and_previous_snapshots(self):
        previous = {}
        changes = 0
        for record in self.trace(self.text, 1):
            if record["event"] == "raw_report":
                continue
            for group, children in record["children"].items():
                if children is None:
                    previous.pop(group, None)
                    continue
                self.assertTrue(children)
                if group == "multibyte_group":
                    self.assertEqual(len(children), 8)
                self.assertEqual([c["index"] for c in children], list(range(len(children))))
                for child in children:
                    current = child["current"]
                    self.assertEqual(child["state_reason"], "unknown")
                    self.assertIn(current["state"], (None, "detecting", "found", "rejected"))
                    self.assertIsInstance(current["active"], bool)
                    self.assertIsInstance(current["present"], bool)
                    if group in previous:
                        expected = previous[group][child["index"]]["current"]
                        self.assertEqual(child["previous"], expected)
                        self.assertEqual(child["changed"], current != expected)
                    else:
                        self.assertIsNone(child["previous"])
                        self.assertIsNone(child["changed"])
                    changes += child["changed"] is True
                previous[group] = children
        self.assertGreater(changes, 0)

    def test_deterministic_and_no_input_body(self):
        first = self.trace(self.text, 7)
        self.assertEqual(first, self.trace(self.text, 7))
        output = json.dumps(first, ensure_ascii=False)
        self.assertNotIn("日本語", output)
        self.assertNotIn(self.text.hex(), output)

    @unittest.skipUnless(os.environ.get("UCHARDET_TRACE_BASELINE"), "set pre-change UCHARDET_TRACE_BASELINE")
    def test_existing_observations_unchanged(self):
        for data in (b"", b"plain text\n", self.text):
            for chunk in (0, 1, 7, 64, 1024):
                current = self.trace(data, chunk)
                for record in current:
                    record.pop("children", None)
                    record.pop("language_detectors", None)
                    record.pop("prober_evidence", None)
                self.assertEqual(current, self.trace(data, chunk, os.environ["UCHARDET_TRACE_BASELINE"]))

    @unittest.skipUnless(os.environ.get("UCHARDET_CONFORMANCE") and os.environ.get("UCHARDET_CONFORMANCE_BASELINE"),
                         "set pre/post-change conformance executables")
    def test_same_feed_candidates_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for index, data in enumerate((b"", b"plain text\n", self.text)):
                path = Path(directory) / str(index)
                path.write_bytes(data)
                paths.append(str(path))
            for mode in ("fresh", "reuse"):
                for chunk in ("0", "1", "7", "64", "1024", "random"):
                    outputs = [subprocess.run([os.environ[key], mode, chunk, *paths], check=True,
                                              capture_output=True, timeout=30).stdout
                               for key in ("UCHARDET_CONFORMANCE_BASELINE", "UCHARDET_CONFORMANCE")]
                    self.assertEqual(*outputs)


if __name__ == "__main__":
    unittest.main()
