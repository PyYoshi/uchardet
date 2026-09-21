# SPDX-License-Identifier: MIT
"""Smoke contracts only; never assert a speed threshold in CI."""

import json
import math
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fixed_block_timing as timing


class TimingDriverTests(unittest.TestCase):
    def test_affinity_required_before_reading_inputs(self):
        with patch.object(timing.os, "sched_getaffinity", return_value={0, 1}, create=True):
            with patch.object(Path, "read_text") as read:
                with self.assertRaises(ValueError):
                    timing.run(Path("unused"), Path("unused"), Path("unused"))
                read.assert_not_called()


@unittest.skipUnless(os.environ.get("UCHARDET_FIXED_BLOCK_TIMING"), "set timing binary")
class TimingNativeTests(unittest.TestCase):
    def invoke(self, block, chunk, iterations, repeats, data=b"plain ASCII text"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(data)
            return subprocess.run(
                [
                    os.environ["UCHARDET_FIXED_BLOCK_TIMING"],
                    str(block),
                    str(chunk),
                    str(iterations),
                    str(repeats),
                    str(path),
                ],
                text=True,
                capture_output=True,
                timeout=10,
            )

    def test_small_measurement_schema_and_result_consumption(self):
        result = self.invoke(7, 1, 2, 3)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(result.stdout)
        self.assertEqual(record["iterations"], 2)
        self.assertEqual(record["repeats"], 3)
        self.assertEqual(set(record["modes"]), {"whole", "direct_fixed", "adapter"})
        for mode in record["modes"].values():
            self.assertEqual(len(mode["trial_mean_ns"]), 3)
            self.assertTrue(all(math.isfinite(v) and v >= 0 for v in mode["trial_mean_ns"]))
            self.assertEqual(len(set(mode["checksums"])), 1)
        self.assertEqual(
            record["modes"]["direct_fixed"]["checksums"], record["modes"]["adapter"]["checksums"]
        )

    def test_invalid_parameters(self):
        for args in (
            (0, 0, 1, 1),
            (4097, 0, 1, 1),
            (7, 0, 0, 1),
            (7, 0, 1, 32),
            (7, -1, 1, 1),
            ("7x", 0, 1, 1),
        ):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_rejects_input_over_pilot_limit(self):
        result = self.invoke(7, 0, 1, 1, b"a" * 4097)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
