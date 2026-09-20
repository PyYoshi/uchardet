# SPDX-License-Identifier: MIT
"""Small input-contract observations, not a detector or fuzz test."""
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get("UCHARDET_FILTER_PROFILE"), "set UCHARDET_FILTER_PROFILE")
class FilterProfileTests(unittest.TestCase):
    def profile(self, data, chunk):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(data)
            result = subprocess.run(
                [os.environ["UCHARDET_FILTER_PROFILE"], str(chunk), str(path)],
                check=True, capture_output=True, text=True, timeout=30,
            )
        return json.loads(result.stdout)

    def check_statistics(self, result, expected):
        self.assertEqual(result["bytes"], len(expected))
        self.assertEqual(result["symbols"], [expected.count(i) for i in range(256)])
        pairs = Counter(zip(expected, expected[1:]))
        self.assertEqual(result["pairs"], [[a, b, n] for (a, b), n in sorted(pairs.items())])

    def test_empty_and_ascii(self):
        for data in (b"", b"plain text\n"):
            result = self.profile(data, 0)
            self.assertEqual(result["schema"], "sbcs-filter-profile-v1")
            self.check_statistics(result["raw"], data)
            self.check_statistics(result["filtered"], b"")
            self.assertEqual(result["calls"], [[len(data), 0]] if data else [])

    def test_whole_word_and_chunk_difference(self):
        data = b"plain caf\xe9 text"
        whole = self.profile(data, 0)
        split = self.profile(data, 1)
        self.check_statistics(whole["raw"], data)
        self.assertEqual(whole["raw"], split["raw"])
        self.check_statistics(whole["filtered"], b"caf\xe9 ")
        self.check_statistics(split["filtered"], b"\xe9")
        self.assertEqual(len(split["calls"]), len(data))

    def test_existing_tiny_multibyte_fixture(self):
        data = "日本語の文章です。".encode() * 5
        for chunk in (0, 1, 7, 64, 1024):
            result = self.profile(data, chunk)
            self.check_statistics(result["raw"], data)
            self.check_statistics(result["filtered"], data)
            self.assertEqual(result, self.profile(data, chunk))
            self.assertNotIn(data.hex(), json.dumps(result))

    def test_invalid_chunk(self):
        for chunk in ("-1", "1x", "65537"):
            with self.assertRaises(subprocess.CalledProcessError):
                self.profile(b"plain text\n", chunk)


if __name__ == "__main__":
    unittest.main()
