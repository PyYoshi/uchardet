# SPDX-License-Identifier: MIT
import copy
import unittest
from unittest.mock import patch

import ratio_chunks


class RatioChunkTests(unittest.TestCase):
    def test_confidence_order_and_lifecycle_are_separate(self):
        base = dict(candidate_count=2, candidates=[
            dict(encoding="cp1252", language="fr", confidence_bits="3f000000"),
            dict(encoding="UTF-8", language=None, confidence_bits="3e000000")],
            final_done=True, first_done_offset=128, feed_calls=1)
        changed = copy.deepcopy(base)
        changed["feed_calls"] = 128
        self.assertFalse(any(ratio_chunks.differences(changed, base).values()))
        changed["candidates"][0]["confidence_bits"] = "3f000001"
        result = ratio_chunks.differences(changed, base)
        self.assertTrue(result["exact_candidates"])
        self.assertFalse(result["encoding_language_order"])
        changed["candidates"].reverse()
        self.assertTrue(ratio_chunks.differences(changed, base)["encoding_language_order"])
        changed["first_done_offset"] = 64
        self.assertTrue(ratio_chunks.differences(changed, base)["first_done_offset"])

    def test_wrong_sweep_rejected_before_process(self):
        with patch.object(ratio_chunks.engine_probe, "observe") as observe:
            with self.assertRaisesRegex(ValueError, "frozen ratio"):
                ratio_chunks.run(None, None, None, None, {}, None)
            observe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
