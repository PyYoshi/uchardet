# SPDX-License-Identifier: MIT
from fractions import Fraction
import unittest

from framework import content_hash
from groups import summarize
from overlap import PROFILE


class GroupTests(unittest.TestCase):
    def report(self, edges=(), splits=("validation",) * 4):
        result = {"profile": PROFILE,
                  "sources": [{"id": str(i), "split": split, "language": "fr"}
                              for i, split in enumerate(splits)],
                  "findings": [{"left": a, "right": b} for a, b in edges],
                  "skipped_independent": []}
        result["content_hash"] = content_hash(result)
        return result

    def test_transitive_candidates_not_clique(self):
        result = summarize(self.report([(0, 1), (1, 2)]))
        self.assertEqual(result["component_count"], 2)
        self.assertEqual(result["components"][0]["members"], [0, 1, 2])
        self.assertEqual(result["components"][0]["candidate_edges"], 2)
        self.assertEqual(result["sources_in_multi_source_components"], 3)

    def test_weight_sum_per_component(self):
        result = summarize(self.report([(0, 1), (2, 3)]))
        for group in result["components"]:
            weight = group["illustrative_member_weight"]
            self.assertEqual(Fraction(weight["numerator"], weight["denominator"]) * group["size"], 1)

    def test_isolated_and_empty(self):
        self.assertEqual(summarize(self.report())["component_count"], 4)
        self.assertEqual(summarize(self.report(splits=()))["component_count"], 0)

    def test_cross_split_group(self):
        result = summarize(self.report([(0, 1)], ("training", "validation")))
        self.assertEqual(result["cross_split_components"], 1)

    def test_invalid_edges(self):
        for edges in ([(0, 0)], [(0, 5)], [(1, 0)], [(True, 2)], [(0, 1), (0, 1)]):
            with self.subTest(edges=edges), self.assertRaises(ValueError):
                summarize(self.report(edges))

    def test_invalid_identity(self):
        report = self.report()
        report["sources"].pop()
        with self.assertRaises(ValueError):
            summarize(report)

    def test_edge_order_does_not_change_components(self):
        first = summarize(self.report([(0, 1), (1, 2)]))
        second = summarize(self.report([(1, 2), (0, 1)]))
        self.assertEqual(first["components"], second["components"])


if __name__ == "__main__":
    unittest.main()
