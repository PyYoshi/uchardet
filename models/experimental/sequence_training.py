# SPDX-License-Identifier: MIT
"""Python-only, uncalibrated training profile; no native detector execution."""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import encodings.cp1252
import json
from pathlib import Path
import platform
import unicodedata

from model import canonical, digest, select, write_idempotent
from sequence_contract import SCHEMA, content_hash, validate as validate_contract

PROFILE = "cp1252-identity-sequence-training-v1"
SPEC = {"filter": "identity-unfiltered-v1", "normalization": "none", "case_folding": False,
        "frequent_letter_limit": 64, "character_tie_break": "byte-ascending",
        "positive_mass_percent": 95, "probable_mass_percent": 99,
        "pair_ties": "same-frequency-group; classify by preceding cumulative mass",
        "unseen_pair_category": 0, "document_boundaries": "no-cross-document-pairs",
        "ratio": "positive-pair-mass/all-adjacent-letter-pair-mass",
        "rounding": "binary32-nearest-ties-even"}


def dependencies():
    base = Path(__file__).resolve().parents[2]
    names = ("models/experimental/sequence_training.py", "models/experimental/model.py",
             "models/experimental/sequence_contract.py", "corpus/framework.py", "corpus/artifact.py")
    result = {name: digest((base / name).read_bytes()) for name in names}
    result["stdlib:encodings.cp1252"] = digest(Path(encodings.cp1252.__file__).read_bytes())
    return result


def runtime():
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "unicode": unicodedata.unidata_version}


def fraction32(bits):
    exponent, mantissa = (bits >> 23) & 255, bits & 0x7fffff
    power = exponent - 150 if exponent else -149
    number = mantissa + (1 << 23) if exponent else mantissa
    return Fraction(number * (1 << max(power, 0)), 1 << max(-power, 0))


def binary32_ratio(numerator, denominator):
    if type(numerator) is not int or type(denominator) is not int or not 0 < numerator <= denominator:
        raise ValueError("ratio needs positive integer mass")
    value = Fraction(numerator, denominator)
    low, high = 0, 0x3f800000
    while low < high:
        middle = (low + high + 1) // 2
        if fraction32(middle) <= value:
            low = middle
        else:
            high = middle - 1
    if fraction32(low) != value:
        lower, upper = value - fraction32(low), fraction32(low + 1) - value
        if upper < lower or (upper == lower and low % 2):
            low += 1
    if low == 0:
        raise ValueError("positive ratio underflows binary32")
    return f"{low:08x}"


def character_classes():
    result = []
    for byte in range(256):
        try:
            char = bytes([byte]).decode("cp1252", errors="strict")
        except UnicodeDecodeError:
            result.append(255)
            continue
        category = unicodedata.category(char)
        result.append("letter" if category.startswith("L") else
                      252 if char in "\r\n" else 254 if category == "Cc" else
                      251 if "0" <= char <= "9" else 253)
    return result


def count_document(data):
    symbols = [0] * 256
    for byte in data:
        symbols[byte] += 1
    pairs = Counter(zip(data, data[1:]))
    return {"byte_count": len(data), "symbols": symbols,
            "pairs": [[a, b, n] for (a, b), n in sorted(pairs.items())]}


def validate_counts(counts):
    symbols = counts["symbols"]
    if not isinstance(symbols, list) or len(symbols) != 256 or any(type(n) is not int or not 0 <= n < 2**64 for n in symbols):
        raise ValueError("invalid symbol counts")
    size = counts["byte_count"]
    if type(size) is not int or not 0 <= size < 2**64 or sum(symbols) != size:
        raise ValueError("invalid byte count")
    incoming, outgoing, previous, total = Counter(), Counter(), (-1, -1), 0
    for row in counts["pairs"]:
        if not isinstance(row, list) or len(row) != 3 or any(type(n) is not int for n in row):
            raise ValueError("invalid pair row")
        a, b, n = row
        if not (0 <= a < 256 and 0 <= b < 256 and 0 < n < 2**64) or (a, b) <= previous:
            raise ValueError("invalid pair ordering/count")
        outgoing[a] += n
        incoming[b] += n
        total += n
        previous = a, b
    if total != max(0, size - 1) or any(incoming[i] > symbols[i] or outgoing[i] > symbols[i] for i in range(256)):
        raise ValueError("pair counts do not match document boundaries")


def derive(documents):
    symbols, pairs = Counter(), Counter()
    for document in documents:
        counts = document["counts"]
        validate_counts(counts)
        symbols.update({i: n for i, n in enumerate(counts["symbols"])})
        pairs.update({(a, b): n for a, b, n in counts["pairs"]})
    classes = character_classes()
    if any(symbols[b] for b in range(256) if classes[b] == 255):
        raise ValueError("undefined cp1252 byte in training counts")
    letters = sorted((b for b in range(256) if classes[b] == "letter" and symbols[b]), key=lambda b: (-symbols[b], b))[:64]
    if not letters:
        raise ValueError("no training letters")
    order = {byte: i for i, byte in enumerate(letters)}
    table = [order.get(b, len(letters)) if classes[b] == "letter" else classes[b] for b in range(256)]
    frequent_pairs = {(order[a], order[b]): n for (a, b), n in pairs.items() if a in order and b in order}
    total = sum(frequent_pairs.values())
    if not total:
        raise ValueError("no adjacent frequent-letter pairs")
    by_count = {}
    for pair, n in frequent_pairs.items():
        by_count.setdefault(n, []).append(pair)
    matrix, cumulative, positive = [0] * len(letters)**2, 0, 0
    for n in sorted(by_count, reverse=True):
        category = 3 if cumulative * 100 < total * 95 else 2 if cumulative * 100 < total * 99 else 1
        mass = n * len(by_count[n])
        for a, b in by_count[n]:
            matrix[a * len(letters) + b] = category
        if category == 3:
            positive += mass
        cumulative += mass
    denominator = sum(n for (a, b), n in pairs.items() if classes[a] == classes[b] == "letter")
    return {"frequent_character_count": len(letters), "byte_to_order": table,
            "pair_categories": matrix, "typical_positive_ratio_bits": binary32_ratio(positive, denominator)}, {
                "positive_pair_mass": positive, "letter_pair_mass": denominator, "frequent_pair_mass": total}


def make_contract(documents, language, corpus_hash, source_hash):
    fields, audit = derive(documents)
    contract = dict(schema=SCHEMA, encoding="cp1252", language=language, **fields,
                    keep_english_letters=True, generated_model_license="UNDETERMINED",
                    generation_parameters={"character_order": PROFILE + ":letters-count-desc-byte-asc",
                        "pair_categories": PROFILE + ":95-99-frequency-ties",
                        "filter": SPEC["filter"], "typical_positive_ratio": SPEC["ratio"],
                        "document_boundaries": SPEC["document_boundaries"]},
                    provenance={"generator_version": PROFILE, "generator_license": "MIT",
                        "generator_source_sha256": source_hash, "corpus_content_hash": corpus_hash,
                        "sources": [d["source"] for d in documents]})
    contract["content_hash"] = content_hash(contract)
    validate_contract(contract)
    return contract, audit


def train(manifest, root, language):
    records = select(manifest, root, language, "training")
    documents = [{"source": source, "sample_sha256": sample["sha256"],
                  "encoder": sample["encoder"], "encoder_version": sample["encoder_version"],
                  "counts": count_document(data)} for source, sample, data in records]
    dep = dependencies()
    contract, audit = make_contract(documents, language, manifest["content_hash"], digest(canonical(dep)))
    result = {"profile": PROFILE, "spec": SPEC.copy(), "deployment_status": "NOT_ENGINE_CALIBRATED",
              "runtime": runtime(),
              "dependencies": dep, "documents": documents, "contract": contract, "audit": audit}
    result["content_hash"] = content_hash(result)
    validate(result)
    return result


def validate(artifact):
    if artifact.get("content_hash") != content_hash(artifact):
        raise ValueError("training artifact hash mismatch")
    if artifact.get("profile") != PROFILE or canonical(artifact.get("spec")) != canonical(SPEC) or artifact.get("deployment_status") != "NOT_ENGINE_CALIBRATED":
        raise ValueError("unsupported training profile/status")
    if artifact.get("dependencies") != dependencies():
        raise ValueError("generator dependency revision mismatch")
    if artifact.get("runtime") != runtime():
        raise ValueError("runtime revision mismatch")
    documents = artifact["documents"]
    if not isinstance(documents, list) or not documents:
        raise ValueError("missing document audit")
    contract = artifact["contract"]
    validate_contract(contract)
    if [d["source"]["id"] for d in documents] != sorted(d["source"]["id"] for d in documents):
        raise ValueError("noncanonical document order")
    for doc in documents:
        if doc["source"]["language"] != contract["language"]:
            raise ValueError("training language mismatch")
        if not isinstance(doc["sample_sha256"], str) or len(doc["sample_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in doc["sample_sha256"]):
            raise ValueError("invalid sample hash")
        for name in ("encoder", "encoder_version"):
            if not isinstance(doc[name], str) or not doc[name]:
                raise ValueError("missing encoder metadata")
    expected, audit = make_contract(documents, contract["language"], contract["provenance"]["corpus_content_hash"], digest(canonical(artifact["dependencies"])))
    if canonical(expected) != canonical(contract) or canonical(audit) != canonical(artifact["audit"]):
        raise ValueError("contract/audit differs from recomputed training counts")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    training = commands.add_parser("train")
    training.add_argument("manifest", type=Path)
    training.add_argument("language")
    training.add_argument("output", type=Path)
    checking = commands.add_parser("validate")
    checking.add_argument("artifact", type=Path)
    checking.add_argument("--manifest", type=Path, help="also regenerate from validated corpus bytes")
    args = parser.parse_args()
    if args.command == "train":
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        write_idempotent(args.output, canonical(train(manifest, args.manifest.parent, args.language)))
    else:
        artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
        validate(artifact)
        if args.manifest:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            if train(manifest, args.manifest.parent, artifact["contract"]["language"]) != artifact:
                raise ValueError("artifact differs from regenerated corpus bytes")


if __name__ == "__main__":
    main()
