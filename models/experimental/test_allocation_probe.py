# SPDX-License-Identifier: MIT
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import sequence_probe


@unittest.skipUnless(
    sys.platform == "linux" and os.environ.get("UCHARDET_STATIC_LIBRARY"),
    "Linux native static library not configured",
)
class AllocationProbeTests(unittest.TestCase):
    def test_counted_reuse_matches_uninstrumented_observation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binaries = []
            for enabled in (False, True):
                directory = root / str(enabled)
                directory.mkdir()
                binary, provenance = sequence_probe.build_reference(
                    os.environ["UCHARDET_STATIC_LIBRARY"],
                    directory,
                    os.environ.get("UCHARDET_PROBE_CXX", "c++"),
                    allocations=enabled,
                )
                self.assertEqual(
                    "-DUCHARDET_ALLOCATION_PROBE" in provenance["flags"], enabled
                )
                binaries.append(binary)
            for data in (b"", b"ASCII words", b"caf\xe9 et th\xe9", b"\xe9" * 2048):
                plain = sequence_probe.observe(binaries[0], data)
                counted = sequence_probe.observe(binaries[1], data)
                counts = counted.pop("allocation_calls")
                self.assertEqual(
                    counts,
                    dict.fromkeys(
                        (
                            "malloc",
                            "calloc",
                            "realloc",
                            "free",
                            "new",
                            "new_array",
                            "delete",
                            "delete_array",
                        ),
                        0,
                    ),
                )
                self.assertEqual(counted, plain)
            rejected = subprocess.run(
                [str(binaries[1]), "unused", "3"], capture_output=True, timeout=10, check=False
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn(b"separate modes", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
