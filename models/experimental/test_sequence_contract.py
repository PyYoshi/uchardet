# SPDX-License-Identifier: MIT
import copy
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from sequence_contract import SCHEMA, content_hash, emit_cpp, ratio, validate
from model import canonical, digest, write_idempotent


def fixture():
    # Original artificial two-symbol model: not a copied or trained language table.
    orders = [253] * 256
    for byte in range(256):
        try:
            bytes([byte]).decode("cp1252")
        except UnicodeDecodeError:
            orders[byte] = 255
    orders[ord("a")], orders[ord("b")] = 0, 1
    data = b"abba"
    source = dict(id="artificial", path="artificial.txt", language="fr", license="MIT",
                  license_reference="corpus/LICENSES/MIT.txt", revision="fixture-v1",
                  origin="synthetic:sequence-contract-v1", kind="synthetic",
                  sha256=digest(data), split="training")
    contract = dict(schema=SCHEMA, encoding="WINDOWS-1252", language="fr",
                    frequent_character_count=2, byte_to_order=orders,
                    pair_categories=[0, 1, 2, 3], typical_positive_ratio_bits="3f400000",
                    keep_english_letters=True, generated_model_license="UNDETERMINED",
                    generation_parameters=dict(character_order="artificial-a-b-order-v1",
                        pair_categories="artificial-four-values-v1", filter="none-fixture-only",
                        typical_positive_ratio="artificial-three-quarters-v1",
                        document_boundaries="no-cross-document-pairs"),
                    provenance=dict(generator_version="synthetic-contract-fixture-v1",
                        generator_license="MIT", generator_source_sha256=digest(Path(__file__).read_bytes()),
                        corpus_content_hash=digest(data), sources=[source]))
    contract["content_hash"] = content_hash(contract)
    return contract


class SequenceContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = fixture()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def assert_invalid(self, contract):
        contract["content_hash"] = content_hash(contract)
        with self.assertRaises(ValueError):
            validate(contract)

    def test_deterministic_idempotent_emission(self):
        validate(self.contract)
        self.assertEqual(ratio(self.contract), 0.75)
        emitted = emit_cpp(self.contract)
        self.assertEqual(emitted, emit_cpp(copy.deepcopy(self.contract)))
        self.assertIn(b"UNDETERMINED", emitted)
        target = self.root / "model.hpp"
        write_idempotent(target, emitted)
        before = target.stat().st_mtime_ns
        write_idempotent(target, emitted)
        self.assertEqual(before, target.stat().st_mtime_ns)
        with self.assertRaises(ValueError):
            write_idempotent(target, b"different model")

    def test_dimensions_categories_and_reserved_orders(self):
        for mutate in (
                lambda c: c.update(frequent_character_count=0),
                lambda c: c.update(frequent_character_count=251),
                lambda c: c.update(frequent_character_count=True),
                lambda c: c["byte_to_order"].pop(),
                lambda c: c["byte_to_order"].__setitem__(0, 250),
                lambda c: c["byte_to_order"].__setitem__(0, 256),
                lambda c: c["byte_to_order"].__setitem__(0, True),
                lambda c: c["pair_categories"].pop(),
                lambda c: c["pair_categories"].__setitem__(0, 4),
                lambda c: c.update(keep_english_letters=1)):
            contract = copy.deepcopy(self.contract)
            mutate(contract)
            self.assert_invalid(contract)

    def test_ratio_bits(self):
        for bits in ("00000000", "80000000", "bf000000", "7f800000", "7fc00000", "40000000", "bad", 1):
            self.assert_invalid(dict(self.contract, typical_positive_ratio_bits=bits))
        for bits in ("00000001", "3eaaaaab", "3f800000"):
            contract = dict(self.contract, typical_positive_ratio_bits=bits)
            contract["content_hash"] = content_hash(contract)
            self.assertIn(b"SequenceModel", emit_cpp(contract))

    def test_provenance_and_parameters_required(self):
        for field in self.contract["generation_parameters"]:
            contract = copy.deepcopy(self.contract)
            del contract["generation_parameters"][field]
            self.assert_invalid(contract)
        for field in ("generator_version", "generator_license", "generator_source_sha256", "corpus_content_hash", "sources"):
            contract = copy.deepcopy(self.contract)
            del contract["provenance"][field]
            self.assert_invalid(contract)
        for mutation in ("training-split", "license", "duplicate"):
            contract = copy.deepcopy(self.contract)
            sources = contract["provenance"]["sources"]
            if mutation == "training-split":
                sources[0]["split"] = "validation"
            elif mutation == "license":
                del sources[0]["license"]
            else:
                sources.append(copy.deepcopy(sources[0]))
            self.assert_invalid(contract)

    def test_raw_model_is_not_silently_converted(self):
        with self.assertRaisesRegex(ValueError, "raw byte counts"):
            validate(dict(model_format_version=1, symbol_counts=[1] * 256))
        self.assert_invalid(dict(self.contract, generated_model_license="MIT"))
        self.assert_invalid(dict(self.contract, encoding='cp1252";'))
        self.assert_invalid(dict(self.contract, encoding="UTF-8"))
        self.assert_invalid(dict(self.contract, language="fr\n"))
        with self.assertRaisesRegex(ValueError, "hash"):
            validate(dict(self.contract, content_hash="0" * 64))

    def test_cli_validate_and_emit(self):
        source = self.root / "model.json"
        source.write_bytes(canonical(self.contract))
        tool = Path(__file__).with_name("sequence_contract.py")
        for args in (["validate", str(source)], ["emit-cpp", str(source), str(self.root / "model.hpp")]):
            subprocess.run([sys.executable, str(tool), *args], check=True, timeout=30)
        self.assertEqual((self.root / "model.hpp").read_bytes(), emit_cpp(self.contract))

    @unittest.skipUnless(shutil.which("g++") or shutil.which("clang++"), "C++ compiler unavailable")
    def test_native_struct_layout_and_binary32_roundtrip(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        native_include = Path(__file__).resolve().parents[2] / "src"
        for bits in ("00000001", "3eaaaaab", "3f400000", "3f800000"):
            with self.subTest(bits=bits):
                contract = dict(self.contract, typical_positive_ratio_bits=bits)
                contract["content_hash"] = content_hash(contract)
                (self.root / "model.hpp").write_bytes(emit_cpp(contract))
                source = self.root / "check.cpp"
                source.write_text('#include "model.hpp"\n#include <cstring>\n#include <cstdint>\n'
                    'int main() { const SequenceModel& m = uchardet_sequence_pilot::model;\n'
                    'std::uint32_t bits; std::memcpy(&bits, &m.mTypicalPositiveRatio, sizeof bits);\n'
                    f'if (bits != 0x{bits}u) return 1;\n'
                    'return !(m.freqCharCount == 2 && m.charToOrderMap[97] == 0 && '
                    'm.charToOrderMap[98] == 1 && m.precedenceMatrix[3] == 3 && '
                    'm.keepEnglishLetter && std::strcmp(m.langName, "fr") == 0 && '
                    'std::strcmp(m.charsetName, "WINDOWS-1252") == 0); }\n', encoding="utf-8")
                executable = self.root / "check.exe"
                subprocess.run([compiler, "-std=c++11", "-Wall", "-Wextra", "-Werror",
                                "-I", str(native_include), str(source), "-o", str(executable)],
                               check=True, timeout=60)
                subprocess.run([str(executable)], check=True, timeout=30)


if __name__ == "__main__":
    unittest.main()
