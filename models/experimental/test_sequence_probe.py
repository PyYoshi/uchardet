# SPDX-License-Identifier: MIT
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sequence_probe
from sequence_contract import content_hash
from test_sequence_contract import fixture


class SequenceProbeGuards(unittest.TestCase):
    def test_input_limit_before_native_execution(self):
        with patch.object(sequence_probe.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "65536"):
                sequence_probe.observe(Path("unused"), b"a" * 65537)
            run.assert_not_called()


@unittest.skipUnless(
    os.environ.get("UCHARDET_STATIC_LIBRARY"), "native static library not configured"
)
class NativeSequenceProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.contract = fixture()
        # Original artificial model: high-byte frequent letters survive the native filter.
        cls.contract["byte_to_order"][0xE9] = 0
        cls.contract["byte_to_order"][0xE0] = 1
        cls.contract["byte_to_order"][0xE8] = 2  # Valid but outside the frequent matrix.
        cls.contract["content_hash"] = content_hash(cls.contract)
        cls.binary, cls.provenance = sequence_probe.build(
            cls.contract,
            Path(os.environ["UCHARDET_STATIC_LIBRARY"]),
            cls.temporary.name,
            os.environ.get("UCHARDET_PROBE_CXX", "c++"),
        )

    def observed(self, data):
        return sequence_probe.observe(self.binary, data)

    def test_native_category_counters_and_negative_confidence(self):
        observation = self.observed(b"\xe9\xe9\xe0\xe0\xe9")
        state = observation["snapshot"]
        self.assertEqual(observation["filtered_bytes"], 5)
        self.assertEqual(state["total_characters"], 5)
        self.assertEqual(state["frequent_characters"], 5)
        self.assertEqual(state["out_characters"], 0)
        self.assertEqual(state["control_characters"], 0)
        self.assertEqual(state["total_sequences"], 4)
        self.assertEqual(state["categories"], [1, 1, 1, 1])
        self.assertEqual(state["last_order"], 0)
        self.assertEqual(state["state"], 0)  # Short evidence does not invoke the shortcut.
        confidence = struct.unpack("!f", bytes.fromhex(state["confidence_bits"]))[0]
        self.assertAlmostEqual(confidence, -11 / 12, places=6)

    def test_rare_letters_count_as_negative_sequences(self):
        state = self.observed(b"\xe9\xe8\xe0")["snapshot"]
        self.assertEqual(state["total_sequences"], 2)
        self.assertEqual(state["categories"], [2, 0, 0, 0])
        self.assertEqual(state["frequent_characters"], 2)
        self.assertEqual(state["out_characters"], 1)

    def test_empty_ascii_and_reset(self):
        expected = dict(
            state=0,
            total_characters=0,
            control_characters=0,
            frequent_characters=0,
            out_characters=0,
            total_sequences=0,
            last_order=255,
            categories=[0, 0, 0, 0],
            confidence_bits="3c23d70a",
        )
        for data in (b"", b"plain ASCII words", b"\xe9\xe0"):
            observation = self.observed(data)
            self.assertEqual(observation["after_reset"], expected)
            if not any(b >= 128 for b in data):
                self.assertEqual(observation["snapshot"], expected)

    def test_shortcut_threshold_is_strict_and_confidence_is_not_clamped(self):
        before = self.observed(b"\xe0" * 1025)["snapshot"]
        after = self.observed(b"\xe0" * 1026)["snapshot"]
        self.assertEqual(before["total_sequences"], 1024)
        self.assertEqual(before["state"], 0)
        self.assertEqual(after["total_sequences"], 1025)
        self.assertEqual(after["state"], 1)
        confidence = struct.unpack("!f", bytes.fromhex(after["confidence_bits"]))[0]
        self.assertGreater(confidence, 1)

    def test_repeat_and_build_provenance(self):
        self.assertEqual(self.observed(b"caf\xe9"), self.observed(b"caf\xe9"))
        self.assertEqual(self.provenance["contract_hash"], self.contract["content_hash"])
        for name in (
            "header_sha256",
            "static_library_sha256",
            "compiler_sha256",
            "probe_binary_sha256",
        ):
            self.assertEqual(len(self.provenance[name]), 64)
        with self.assertRaisesRegex(ValueError, "already exists"):
            sequence_probe.build(
                self.contract, Path(os.environ["UCHARDET_STATIC_LIBRARY"]), self.temporary.name
            )


if __name__ == "__main__":
    unittest.main()
