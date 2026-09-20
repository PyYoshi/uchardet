# SPDX-License-Identifier: MIT
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import engine_probe
from sequence_contract import content_hash
from test_sequence_contract import fixture


class EngineProbeGuards(unittest.TestCase):
    def test_rejects_large_input_and_unknown_schedule_before_execution(self):
        with patch.object(engine_probe.subprocess, "run") as run:
            for data, chunk in ((b"x" * 4097, 0), (b"", True), (b"", 2)):
                with self.assertRaises(ValueError):
                    engine_probe.observe(Path("unused"), data, chunk)
            run.assert_not_called()

    def test_unknown_training_profile_is_not_emitted(self):
        with self.assertRaises(ValueError):
            engine_probe.training_contract({"profile": "unknown"})

    def test_rejects_other_language_slot(self):
        contract = fixture()
        contract["language"] = "de"
        contract["provenance"]["sources"][0]["language"] = "de"
        contract["content_hash"] = content_hash(contract)
        with patch.object(engine_probe.sys, "platform", "linux"):
            with self.assertRaises(ValueError):
                engine_probe.build(contract, "unused")


@unittest.skipUnless(os.environ.get("UCHARDET_ENGINE_EXPERIMENT"), "opt-in engine build disabled")
class NativeEngineProbeTests(unittest.TestCase):
    def test_reference_adapter_and_generated_slot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference, _ = engine_probe.build(None, root / "reference")
            for file in sorted((engine_probe.BASE / "test/fr").iterdir()):
                for chunk in (0, 7):
                    records = [engine_probe.observe(binary, file.read_bytes(), chunk) for binary in reference]
                    self.assertEqual(*records)
            contract = fixture()
            contract["byte_to_order"][0xe9] = 0
            contract["content_hash"] = content_hash(contract)
            generated, provenance = engine_probe.build(contract, root / "generated")
            self.assertEqual(provenance["contract_hash"], contract["content_hash"])
            # A deliberate low-quality artificial table must affect the candidate records.
            data = (engine_probe.BASE / "test/fr/windows-1252.txt").read_bytes()
            self.assertNotEqual(*(engine_probe.observe(binary, data) for binary in generated))
            # The normal target in the same build must remain the reference detector.
            self.assertEqual(engine_probe.observe(reference[0], data),
                             engine_probe.observe(generated[0], data))
            oversized = root / "oversized.bin"
            oversized.write_bytes(b"a" * 4097)
            result = subprocess.run([str(generated[1]), "fresh", "0", str(oversized)],
                                    check=False, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"4096", result.stderr)
            subprocess.run(["cmake", "--install", str(root / "generated/build"),
                            "--prefix", str(root / "installed")], check=True,
                           capture_output=True, timeout=30)
            installed = (root / "generated/build/install_manifest.txt").read_text().splitlines()
            self.assertTrue(installed)
            self.assertFalse(any("experimental" in Path(path).name for path in installed))
            self.assertFalse(any(Path(path).name == "model.hpp" for path in installed))
            with self.assertRaises(ValueError):
                engine_probe.build(None, root / "reference")


if __name__ == "__main__":
    unittest.main()
