# SPDX-License-Identifier: MIT
import copy
import unittest
from pathlib import Path
from unittest.mock import patch

import ratio_sweep


class RatioSweepTests(unittest.TestCase):
    def test_gate_requires_improvement_without_regressions(self):
        base = {"cp1252": {"decoded": 4, "exact": 1, "language": 8},
                "utf-8": {"decoded": 8, "exact": 8, "language": 8}, "invalid_confidences": 0}
        self.assertFalse(ratio_sweep.eligible(base, base))
        candidate = copy.deepcopy(base)
        candidate["cp1252"]["decoded"] = 5
        self.assertTrue(ratio_sweep.eligible(candidate, base))
        for encoding, key in (("cp1252", "language"), ("utf-8", "language"),
                              ("utf-8", "exact"), ("utf-8", "decoded")):
            bad = copy.deepcopy(candidate)
            bad[encoding][key] -= 1
            self.assertFalse(ratio_sweep.eligible(bad, base))
        candidate["invalid_confidences"] = 1
        self.assertFalse(ratio_sweep.eligible(candidate, base))

    def test_confidence_gate_includes_non_top_candidates(self):
        score = dict(top1_exact_codec=True, top1_decode_status="equal",
                     top1_language_match=True, expected_candidate_ranks=[1])
        for bits in ("7fc00000", "7f800000", "bf000000", "3f800001"):
            row = dict(encoding="cp1252", score=score, observation={"candidates": [
                {"confidence_bits": "3f800000"}, {"confidence_bits": bits}]})
            self.assertEqual(ratio_sweep.summarize([row])["invalid_confidences"], 1)

    def test_wrong_baseline_rejected_before_build_or_read(self):
        with patch.object(ratio_sweep.engine_probe, "build") as build:
            with self.assertRaisesRegex(ValueError, "frozen Paris24"):
                ratio_sweep.run(None, None, None, None, {}, Path("unused"))
            build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
