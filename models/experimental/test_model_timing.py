# SPDX-License-Identifier: MIT
import unittest
from unittest.mock import patch

import model_timing


class ModelTimingTests(unittest.TestCase):
    def test_trial_summary_and_nearest_rank(self):
        result = model_timing.summary([300, 100, 200], 10)
        self.assertEqual(
            result,
            dict(
                median_ns_per_iteration=20,
                minimum_ns_per_iteration=10,
                maximum_ns_per_iteration=30,
                p95_trial_mean_ns_per_iteration=30,
            ),
        )
        self.assertEqual(
            model_timing.summary(list(range(1, 21)), 1)["p95_trial_mean_ns_per_iteration"], 19
        )

    def test_bad_times_and_iteration_counts(self):
        for values in ([], [0], [-1], [True], [1.5]):
            with self.assertRaises(ValueError):
                model_timing.summary(values, 1)
        for count in (0, -1, 1000001, True):
            with self.assertRaises(ValueError):
                model_timing.summary([1], count)

    def test_requires_single_cpu(self):
        with patch.object(model_timing.os, "sched_getaffinity", return_value={2, 3}, create=True):
            with self.assertRaisesRegex(ValueError, "taskset"):
                model_timing.affinity()
        with patch.object(model_timing.os, "sched_getaffinity", return_value={2}, create=True):
            self.assertEqual(model_timing.affinity(), [2])

    def test_runner_configuration_rejected_before_corpus_or_compile(self):
        for iterations, repeats in ((0, 7), (1, 2), (1, 32), (True, 7), (1, True)):
            with self.assertRaises(ValueError):
                model_timing.run(None, None, None, None, None, None, iterations, repeats)


if __name__ == "__main__":
    unittest.main()
