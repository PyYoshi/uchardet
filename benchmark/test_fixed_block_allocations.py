# SPDX-License-Identifier: MIT
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from fixed_block_allocations import signature


class AllocationSignatureTests(unittest.TestCase):
    def test_language_presence_and_confidence_bits_are_preserved(self):
        record = dict(
            final_done=False,
            candidate_count=1,
            candidates=[dict(encoding="ASCII", language=None, confidence_bits="00000000")],
        )
        original = signature(record)
        record["candidates"][0]["language"] = ""
        self.assertNotEqual(signature(record), original)
        record["candidates"][0]["language"] = None
        record["candidates"][0]["confidence_bits"] = "80000000"
        self.assertNotEqual(signature(record), original)


@unittest.skipUnless(
    os.environ.get("UCHARDET_FIXED_BLOCK_ALLOCATIONS")
    and os.environ.get("UCHARDET_FIXED_BLOCK_ALLOCATIONS_PLAIN"),
    "set allocation binaries",
)
class AllocationNativeTests(unittest.TestCase):
    def invoke(self, binary, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(data)
            return subprocess.run([binary, str(path)], capture_output=True, text=True, timeout=10)

    def test_plain_and_instrumented_results_match(self):
        for data in (b"", b"ASCII", "café et thé".encode("cp1252"), "日本語".encode()):
            outputs = []
            for name in (
                "UCHARDET_FIXED_BLOCK_ALLOCATIONS_PLAIN",
                "UCHARDET_FIXED_BLOCK_ALLOCATIONS",
            ):
                result = self.invoke(os.environ[name], data)
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs.append(json.loads(result.stdout))
            plain, counted = outputs
            for mode in counted["modes"]:
                self.assertEqual(
                    plain["modes"][mode]["snapshot"], counted["modes"][mode]["snapshot"]
                )
            for mode in ("adapter_whole", "adapter_byte"):
                self.assertEqual(
                    counted["modes"][mode]["snapshot"], counted["modes"]["direct_fixed"]["snapshot"]
                )
                self.assertEqual(
                    counted["modes"][mode]["construction"]["new"],
                    counted["modes"]["direct_fixed"]["construction"]["new"] + 1,
                )

    def test_input_cap(self):
        result = self.invoke(os.environ["UCHARDET_FIXED_BLOCK_ALLOCATIONS"], b"a" * 4097)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
