# SPDX-License-Identifier: MIT
"""Read-only prober evidence using the established three tiny fixtures."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get("UCHARDET_TRACE"), "set UCHARDET_TRACE")
class ProberEvidenceTests(unittest.TestCase):
    text = "日本語の文章です。".encode() * 5

    def trace(self, data, chunk, tool=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(data)
            result = subprocess.run(
                [tool or os.environ["UCHARDET_TRACE"], str(chunk), str(path)],
                check=True, capture_output=True, text=True, timeout=30,
            )
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_unallocated_is_null(self):
        for data in (b"", b"plain text\n"):
            for record in self.trace(data, 7):
                if record["event"] != "raw_report":
                    self.assertEqual(record["prober_evidence"], {
                        "multibyte_machines": None, "singlebyte_models": None,
                    })

    def test_initialized_machine_states_and_model_counters(self):
        observed = False
        for record in self.trace(self.text, 7):
            if record["event"] == "raw_report":
                continue
            evidence = record["prober_evidence"]
            machines = evidence["multibyte_machines"]
            if machines is None:
                continue
            observed = True
            self.assertEqual([m["prober_index"] for m in machines], list(range(8)))
            self.assertIsNone(machines[5]["coding_state"])  # Big5 custom logic.
            for machine in machines:
                if machine["prober_index"] != 5:
                    self.assertIsInstance(machine["coding_state"], int)
                    self.assertGreaterEqual(machine["coding_state"], 0)
            models = evidence["singlebyte_models"]
            self.assertTrue(models)
            indices = [m["prober_index"] for m in models]
            self.assertEqual(indices, sorted(set(indices)))
            # The auxiliary Hebrew name prober is not a statistical model.
            self.assertEqual(len(models), len(record["children"]["singlebyte_group"]) - 1)
            for model in models:
                self.assertTrue(model["model_encoding"])
                self.assertTrue(model["model_language"])
                self.assertIsInstance(model["reversed"], bool)
                self.assertEqual(len(model["sequence_categories"]), 4)
                self.assertTrue(all(n >= 0 for n in model["sequence_categories"]))
                self.assertEqual(sum(model["sequence_categories"]), model["total_sequences"])
                for key in ("total_characters", "control_characters",
                            "frequent_characters", "out_characters", "total_sequences"):
                    self.assertGreaterEqual(model[key], 0)
        self.assertTrue(observed)

    def test_deterministic_without_input_body(self):
        first = self.trace(self.text, 1)
        self.assertEqual(first, self.trace(self.text, 1))
        self.assertNotIn("日本語", json.dumps(first, ensure_ascii=False))
        self.assertNotIn(self.text.hex(), json.dumps(first))

    @unittest.skipUnless(os.environ.get("UCHARDET_PROBER_TRACE_BASELINE"),
                         "set baseline with language snapshots but no prober evidence")
    def test_prior_snapshots_and_reports_unchanged(self):
        for data in (b"", b"plain text\n", self.text):
            for chunk in (0, 1, 7, 64, 1024):
                current = self.trace(data, chunk)
                for record in current:
                    record.pop("prober_evidence", None)
                baseline = self.trace(data, chunk, os.environ["UCHARDET_PROBER_TRACE_BASELINE"])
                self.assertEqual(current, baseline)


if __name__ == "__main__":
    unittest.main()
