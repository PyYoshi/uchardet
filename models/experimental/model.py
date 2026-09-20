# SPDX-License-Identifier: MIT
"""Original, offline byte-count model pilot; NOT an uchardet SequenceModel."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "corpus"))
from framework import check_source, digest, safe_path, validate as validate_corpus  # noqa: E402
from artifact import write_idempotent  # noqa: E402

VERSION = "byte-bigram-pilot-v1"


def canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def model_hash(value: dict) -> str:
    return digest(canonical({key: data for key, data in value.items() if key != "content_hash"}))


def select(manifest: dict, root: Path, language: str, split: str) -> list[tuple[dict, dict, bytes]]:
    validate_corpus(manifest, root)
    sources = {source["id"]: source for source in manifest["sources"]}
    selected, seen = [], set()
    for sample in manifest["samples"]:
        source = sources[sample["source_id"]]
        if source["language"] != language or source["split"] != split:
            continue
        if sample["encoding"] != "cp1252" or sample["format"] != "text" or sample["boundary"] != "complete" or sample["byte_limit"] is not None:
            continue
        # Count each source once: size/HTML/truncation variants are not training data.
        if source["sha256"] in seen:
            raise ValueError("duplicate full training/evaluation document")
        seen.add(source["sha256"])
        selected.append((source, sample, safe_path(root, sample["path"]).read_bytes()))
    if not selected:
        raise ValueError(f"no full cp1252 text documents for {language}/{split}")
    return sorted(selected, key=lambda record: record[0]["id"])


def train(manifest: dict, root: Path, language: str) -> dict:
    records = select(manifest, root, language, "training")
    counts, bigrams = [0] * 256, Counter()
    provenance = []
    for source, sample, data in records:
        for byte in data:
            counts[byte] += 1
        bigrams.update(zip(data, data[1:]))  # Never create cross-document pairs.
        provenance.append({"source": source, "sample_sha256": sample["sha256"],
                           "encoder": sample["encoder"], "encoder_version": sample["encoder_version"]})
    if not sum(counts):
        raise ValueError("empty training data")
    model = {"model_format_version": 1, "generator_version": VERSION,
             "generator_source_sha256": digest(Path(__file__).read_bytes()),
             "generator_license": "MIT", "generated_model_license": "UNDETERMINED",
             "encoding": "cp1252", "language": language,
             "parameters": {"alphabet_size": 256, "normalization": "none", "smoothing_alpha": 1,
                            "cross_document_bigrams": False, "selection": "full-complete-text-training"},
             "corpus_content_hash": manifest["content_hash"], "sources": provenance,
             "symbol_counts": counts, "bigrams": [[a, b, count] for (a, b), count in sorted(bigrams.items())],
             "byte_count": sum(counts), "pair_count": sum(bigrams.values())}
    model["content_hash"] = model_hash(model)
    validate_model(model)
    return model


def validate_model(model: dict) -> None:
    if model.get("model_format_version") != 1 or model.get("generator_version") != VERSION:
        raise ValueError("unsupported model format/generator")
    if model.get("encoding") != "cp1252" or model.get("content_hash") != model_hash(model):
        raise ValueError("encoding/hash mismatch")
    if model.get("generator_license") != "MIT" or model.get("generated_model_license") != "UNDETERMINED":
        raise ValueError("unsupported license metadata")
    counts = model["symbol_counts"]
    if len(counts) != 256 or any(type(n) is not int or not 0 <= n < 2**64 for n in counts):
        raise ValueError("symbol table dimension/value")
    previous, outgoing, incoming = (-1, -1), Counter(), Counter()
    total = 0
    for row in model["bigrams"]:
        if len(row) != 3 or any(type(n) is not int for n in row):
            raise ValueError("bigram row format")
        a, b, count = row
        if not (0 <= a < 256 and 0 <= b < 256 and 0 < count < 2**64) or (a, b) <= previous:
            raise ValueError("bigram ordering/value")
        outgoing[a] += count
        incoming[b] += count
        total += count
        previous = a, b
    if any(outgoing[i] > counts[i] or incoming[i] > counts[i] for i in range(256)):
        raise ValueError("bigram exceeds symbol counts")
    if model["byte_count"] != sum(counts) or model["pair_count"] != total:
        raise ValueError("total count mismatch")
    if model["parameters"] != {"alphabet_size": 256, "normalization": "none", "smoothing_alpha": 1,
                               "cross_document_bigrams": False, "selection": "full-complete-text-training"}:
        raise ValueError("unsupported model parameters")
    if not model["sources"] or any(p["source"]["split"] != "training" for p in model["sources"]):
        raise ValueError("non-training model provenance")
    for provenance in model["sources"]:
        check_source(provenance["source"])


def emit_cpp(model: dict) -> bytes:
    validate_model(model)
    counts = ", ".join(f"{count}ULL" for count in model["symbol_counts"])
    rows = ",\n".join(f"    {{{a}, {b}, {count}ULL}}" for a, b, count in model["bigrams"])
    # No SPDX assignment here: generated data rights are not generator rights.
    return (f"// Experimental generated data; license: {model['generated_model_license']}\n"
            f"// Model SHA-256: {model['content_hash']}\n"
            "#pragma once\n#include <array>\n#include <cstdint>\n"
            "namespace uchardet_model_pilot {\n"
            "struct Pair { std::uint8_t first; std::uint8_t second; std::uint64_t count; };\n"
            f"constexpr std::array<std::uint64_t, 256> symbols = {{{{{counts}}}}};\n"
            f"constexpr std::array<Pair, {len(model['bigrams'])}> pairs = {{{{\n{rows}\n}}}};\n"
            'static_assert(symbols.size() == 256, "byte alphabet size");\n'
            f'static_assert(pairs.size() == {len(model["bigrams"])}, "pair table size");\n'
            "} // namespace uchardet_model_pilot\n").encode("utf-8")


def score(model: dict, manifest: dict, root: Path, split: str) -> dict:
    validate_model(model)
    if split not in {"tuning", "validation", "independent"}:
        raise ValueError("scoring requires a non-training split")
    records = select(manifest, root, model["language"], split)
    trained_hashes = {p["source"]["sha256"] for p in model["sources"]}
    trained_origins = {p["source"]["origin"] for p in model["sources"]}
    pairs = {(a, b): count for a, b, count in model["bigrams"]}
    outgoing = Counter()
    for a, _, count in model["bigrams"]:
        outgoing[a] += count
    samples = []
    for source, sample, data in records:
        if source["sha256"] in trained_hashes or source["origin"] in trained_origins:
            raise ValueError("training/heldout leakage across manifests")
        loss = -sum(math.log2((pairs.get((a, b), 0) + 1) / (outgoing[a] + 256))
                    for a, b in zip(data, data[1:]))
        count = max(0, len(data) - 1)
        samples.append({"source_id": source["id"], "kind": source["kind"], "sample_sha256": sample["sha256"],
                        "pair_count": count, "bits_per_pair": loss / count if count else None})
    return {"model_content_hash": model["content_hash"], "corpus_content_hash": manifest["content_hash"],
            "split": split, "metric": "laplace-smoothed byte bigram log loss; NOT encoding accuracy",
            "synthetic_only": all(source["kind"] == "synthetic" for source, _, _ in records), "samples": samples}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("train")
    build.add_argument("manifest", type=Path)
    build.add_argument("language")
    build.add_argument("output", type=Path)
    emit = commands.add_parser("emit-cpp")
    emit.add_argument("model", type=Path)
    emit.add_argument("output", type=Path)
    evaluate = commands.add_parser("score")
    evaluate.add_argument("model", type=Path)
    evaluate.add_argument("manifest", type=Path)
    evaluate.add_argument("split", choices=["tuning", "validation", "independent"])
    evaluate.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "train":
        data = canonical(train(load(args.manifest), args.manifest.parent, args.language))
    elif args.command == "emit-cpp":
        data = emit_cpp(load(args.model))
    else:
        data = canonical(score(load(args.model), load(args.manifest), args.manifest.parent, args.split))
    write_idempotent(args.output, data)


if __name__ == "__main__":
    main()
