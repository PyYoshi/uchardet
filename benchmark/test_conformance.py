# SPDX-License-Identifier: MIT
# Copyright (c) 2026 cChardet contributors
import unittest
from conformance import differences, fixtures


class ConformanceTests(unittest.TestCase):
    def test_fixtures_repeat(self):
        self.assertEqual(fixtures(), fixtures())
        self.assertEqual(fixtures()["empty"], b"")
        self.assertIn(b"\0", fixtures()["embedded-nul"])

    def test_exact_and_chunk_observations_are_separate(self):
        record = {"candidates": [], "initial_done": False, "final_done": False, "feed_calls": 1}
        other = dict(record, feed_calls=2)
        self.assertEqual(len(differences([record], [other], "same-feed")), 1)
        self.assertEqual(differences([record], [other], "chunks", exact=False), [])

    def test_candidate_order_and_bits_are_significant(self):
        candidates = [{"encoding": "UTF-8", "confidence_bits": "3f800000"},
                      {"encoding": "ASCII", "confidence_bits": "3f800000"}]
        self.assertTrue(differences([{"candidates": candidates}],
                                    [{"candidates": candidates[::-1]}], "order"))
        self.assertTrue(differences([{"bits": "00000000"}], [{"bits": "80000000"}], "bits"))

    def test_length_mismatch_fails(self):
        with self.assertRaises(ValueError):
            differences([{}], [], "missing")


if __name__ == "__main__":
    unittest.main()
