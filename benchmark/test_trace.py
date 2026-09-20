# SPDX-License-Identifier: MIT
# Copyright (c) 2026 cChardet contributors
"""Run with UCHARDET_TRACE pointing to an opt-in static diagnostic build."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get("UCHARDET_TRACE"), "set UCHARDET_TRACE to diagnostic executable")
class TraceTests(unittest.TestCase):
    def trace(self, data, chunk):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(data)
            result = subprocess.run([os.environ["UCHARDET_TRACE"], str(chunk), str(path)],
                                    check=True, capture_output=True, text=True, timeout=30)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_minimal_utf8_bom_boundary(self):
        whole = self.trace(b"\xef\xbb\xbf", 0)
        split = self.trace(b"\xef\xbb\xbf", 1)
        self.assertEqual(whole[1]["shortcut_encoding"], "UTF-8")
        self.assertTrue(whole[1]["done"])
        self.assertFalse(split[1]["start"])
        self.assertIsNone(split[1]["shortcut_encoding"])
        self.assertTrue(all(e.get("shortcut_encoding") is None for e in split))

    def test_minimal_utf16_bom_length_gate(self):
        short = self.trace(b"\xff\xfe", 0)
        longer = self.trace(b"\xff\xfe\0", 0)
        self.assertIsNone(short[1]["shortcut_encoding"])
        self.assertEqual(longer[1]["shortcut_encoding"], "UTF-16")

    def test_determinism(self):
        data = "日本語の文章です。".encode() * 5
        self.assertEqual(self.trace(data, 7), self.trace(data, 7))

    def test_empty(self):
        events = self.trace(b"", 1)
        self.assertFalse(events[-1]["got_data"])
        self.assertFalse(events[-1]["done"])

    def test_bounded_input(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.trace(b"x" * 65537, 0)


if __name__ == "__main__":
    unittest.main()
