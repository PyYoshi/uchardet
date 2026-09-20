# SPDX-License-Identifier: MIT
import unittest
from unittest.mock import patch

import engine_comparison as comparison


class EngineComparisonTests(unittest.TestCase):
    def test_alias_exact_and_decode_equivalence_are_separate(self):
        record = {"candidates": [{"encoding": "ISO-8859-1", "language": "fr"},
                                 {"encoding": "WINDOWS-1252", "language": "fr"}]}
        result = comparison.score(record, b"caf\xe9", "cp1252", "fr")
        self.assertFalse(result["top1_exact_codec"])
        self.assertEqual(result["expected_candidate_ranks"], [2])
        self.assertEqual(result["top1_decode_status"], "equal")
        self.assertTrue(result["top1_language_match"])
        self.assertEqual(comparison.score(record, b"\x80", "cp1252", "fr")["top1_decode_status"], "different")
        record["candidates"].reverse()
        self.assertTrue(comparison.score(record, b"\x80", "cp1252", "fr")["top1_exact_codec"])

    def test_unknown_codec_empty_and_decode_error(self):
        for candidates, expected in (([], "no_candidate"),
                ([{"encoding": "X-UNKNOWN", "language": None}], "unknown_codec"),
                ([{"encoding": "UTF-8", "language": "fr"}], "decode_error")):
            result = comparison.score({"candidates": candidates}, b"\xe9", "cp1252", "fr")
            self.assertEqual(result["top1_decode_status"], expected)

    def test_large_input_rejected_before_any_build_or_process(self):
        with patch.object(comparison.paired_controls, "select_pairs", return_value=([({}, {}, b"a" * 4097)], [])):
            with patch.object(comparison, "verified_build") as build:
                with self.assertRaisesRegex(ValueError, "4096"):
                    comparison.compare(None, None, None, None, "validation", None, None)
                build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
