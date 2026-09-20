# SPDX-License-Identifier: MIT
"""Validate an explicit SequenceModel bridge; never infer it from raw byte counts."""

from __future__ import annotations

import argparse
import codecs
import json
import math
from pathlib import Path
import re
import struct

from model import canonical, digest, write_idempotent
from framework import check_source

SCHEMA = "uchardet-sequence-model-v1"
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def content_hash(contract: dict) -> str:
    return digest(canonical({k: v for k, v in contract.items() if k != "content_hash"}))


def required_text(record: dict, names: tuple[str, ...]) -> None:
    for name in names:
        if not isinstance(record.get(name), str) or not record[name].strip():
            raise ValueError(f"missing {name}")


def ratio(contract: dict) -> float:
    bits = contract.get("typical_positive_ratio_bits")
    if not isinstance(bits, str) or not re.fullmatch(r"[0-9a-f]{8}", bits):
        raise ValueError("ratio must be canonical binary32 hex bits")
    value = struct.unpack("!f", bytes.fromhex(bits))[0]
    if not math.isfinite(value) or not 0 < value <= 1:
        raise ValueError("ratio must be finite and in (0, 1]")
    return value


def validate(contract: dict) -> None:
    if contract.get("schema") != SCHEMA:
        raise ValueError("unsupported sequence contract; raw byte counts are not a SequenceModel")
    if contract.get("content_hash") != content_hash(contract):
        raise ValueError("sequence contract content hash mismatch")
    for name in ("encoding", "language"):
        if not isinstance(contract.get(name), str) or not TOKEN.fullmatch(contract[name]):
            raise ValueError(f"invalid {name} token")
    try:
        encoding = codecs.lookup(contract["encoding"]).name
    except LookupError as error:
        raise ValueError("unknown encoding") from error
    if encoding != "cp1252":
        raise ValueError("v1 bridge is limited to cp1252")
    count = contract.get("frequent_character_count")
    if type(count) is not int or not 1 <= count <= 250:
        raise ValueError("frequent character count must be in [1, 250]")
    orders = contract.get("byte_to_order")
    if not isinstance(orders, list) or len(orders) != 256 or any(
            type(n) is not int or not (0 <= n < 250 or 251 <= n <= 255) for n in orders):
        raise ValueError("expected 256 character orders; order 250 is reserved")
    for byte in range(256):
        try:
            bytes([byte]).decode(encoding, errors="strict")
        except UnicodeDecodeError:
            if orders[byte] != 255:
                raise ValueError("undefined cp1252 byte must have illegal order 255")
    categories = contract.get("pair_categories")
    if not isinstance(categories, list) or len(categories) != count * count or any(
            type(n) is not int or not 0 <= n <= 3 for n in categories):
        raise ValueError("expected count-squared matrix with categories 0..3")
    ratio(contract)
    if type(contract.get("keep_english_letters")) is not bool:
        raise ValueError("keep_english_letters must be a boolean")
    if contract.get("generated_model_license") != "UNDETERMINED":
        raise ValueError("generated model distribution license requires a separate decision")
    parameters = contract.get("generation_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("missing generation parameters")
    required_text(parameters, ("character_order", "pair_categories", "filter",
                               "typical_positive_ratio", "document_boundaries"))
    provenance = contract.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("missing provenance")
    required_text(provenance, ("generator_version", "generator_license"))
    for name in ("generator_source_sha256", "corpus_content_hash"):
        value = provenance.get(name)
        if not isinstance(value, str) or not SHA256.fullmatch(value):
            raise ValueError(f"invalid {name}")
    sources = provenance.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("missing training source provenance")
    seen_hashes, seen_origins = set(), set()
    for source in sources:
        check_source(source)
        if source["split"] != "training":
            raise ValueError("non-training source in model provenance")
        if source["sha256"] in seen_hashes or source["origin"] in seen_origins:
            raise ValueError("duplicate training source")
        seen_hashes.add(source["sha256"])
        seen_origins.add(source["origin"])


def emit_cpp(contract: dict) -> bytes:
    validate(contract)
    orders = ", ".join(map(str, contract["byte_to_order"]))
    pairs = ", ".join(map(str, contract["pair_categories"]))
    # Nine significant decimal digits round-trip binary32; C++11 has no hex float literals.
    literal = format(ratio(contract), ".9g")
    if "." not in literal and "e" not in literal:
        literal += ".0"
    keep = "PR_TRUE" if contract["keep_english_letters"] else "PR_FALSE"
    return ("// Experimental generated model; distribution license: UNDETERMINED\n"
            f"// Contract SHA-256: {contract['content_hash']}\n"
            "// Tool license is not a license grant for the input model data.\n"
            "#pragma once\n#include <limits>\n#include \"nsSBCharSetProber.h\"\n"
            "namespace uchardet_sequence_pilot {\n"
            'static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559, "binary32 required");\n'
            f"static const unsigned char byte_to_order[256] = {{{orders}}};\n"
            f"static const PRUint8 pair_categories[{len(contract['pair_categories'])}] = {{{pairs}}};\n"
            "static const SequenceModel model = {\n"
            f"    byte_to_order, pair_categories, {contract['frequent_character_count']},\n"
            f"    {literal}f, {keep}, \"{contract['encoding']}\", \"{contract['language']}\"\n"
            "};\n} // namespace uchardet_sequence_pilot\n").encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("contract", type=Path)
    emit_parser = commands.add_parser("emit-cpp")
    emit_parser.add_argument("contract", type=Path)
    emit_parser.add_argument("output", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    validate(contract)
    if args.command == "emit-cpp":
        write_idempotent(args.output, emit_cpp(contract))


if __name__ == "__main__":
    main()
