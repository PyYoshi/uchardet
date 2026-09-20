# SPDX-License-Identifier: MIT
import copy
import unittest

import ratio_variant as variant
from model import canonical
from sequence_contract import content_hash, ratio
import test_sequence_training as training_fixtures


class RatioVariantTests(unittest.TestCase):
    def setUp(self):
        fixture = training_fixtures.SequenceTrainingTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.parent = fixture.artifact

    def test_identity_preserves_exact_contract(self):
        result = variant.derive(self.parent, "1")
        self.assertEqual(canonical(result["contract"]), canonical(self.parent["contract"]))
        variant.validate(result, self.parent)

    def test_frozen_grid_preserves_tables_sources_and_parent(self):
        before = canonical(self.parent)
        for factor in variant.FACTORS:
            result = variant.derive(self.parent, factor)
            variant.validate(result, self.parent)
            self.assertEqual(result, variant.derive(self.parent, factor))
            for field in ("byte_to_order", "pair_categories", "frequent_character_count",
                          "encoding", "language", "generated_model_license", "keep_english_letters"):
                self.assertEqual(result["contract"][field], self.parent["contract"][field])
            self.assertEqual(result["contract"]["provenance"]["sources"], self.parent["contract"]["provenance"]["sources"])
            self.assertAlmostEqual(ratio(result["contract"]), ratio(self.parent["contract"]) * float(factor), places=6)
        self.assertEqual(before, canonical(self.parent))

    def test_arbitrary_factor_and_rehashed_tampering_rejected(self):
        for factor in (None, True, 0.9, "0.5", "nan"):
            with self.assertRaises(ValueError):
                variant.derive(self.parent, factor)
        result = variant.derive(self.parent, "0.90")
        changed = copy.deepcopy(result)
        changed["contract"]["pair_categories"][0] ^= 1
        changed["contract"]["content_hash"] = content_hash(changed["contract"])
        changed["content_hash"] = content_hash(changed)
        with self.assertRaises(ValueError):
            variant.validate(changed, self.parent)


if __name__ == "__main__":
    unittest.main()
