# SPDX-License-Identifier: MIT
"""Python-only fixed-table coverage diagnostics; not detector accuracy/confidence."""
from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path

from model import canonical, digest, safe_path, write_idempotent
from framework import validate as validate_corpus
from sequence_training import character_classes, dependencies as training_dependencies, runtime, validate as validate_training

VERSION = "sequence-coverage-evaluation-v2"
SIZE_BOUNDS = (16, 32, 64, 128, 256, 512, 1024, 4096, 16384, 65536, 262144)
COUNTERS = ("bytes", "letters", "frequent_letters", "known_rare_letters", "unknown_letters",
            "adjacent_letter_pairs", "matrix_pairs", "outside_matrix_pairs", "unseen_matrix_pairs")


def counts(data, contract, known_letters):
    classes = character_classes()
    orders, size = contract["byte_to_order"], contract["frequent_character_count"]
    result = {key: 0 for key in COUNTERS}
    result["bytes"] = len(data)
    result["category_mass"] = [0, 0, 0, 0]
    for byte in data:
        if classes[byte] != "letter":
            continue
        result["letters"] += 1
        key = "frequent_letters" if orders[byte] < size else "known_rare_letters" if byte in known_letters else "unknown_letters"
        result[key] += 1
    for a, b in zip(data, data[1:]):
        if classes[a] != "letter" or classes[b] != "letter":
            continue
        result["adjacent_letter_pairs"] += 1
        if orders[a] >= size or orders[b] >= size:
            result["outside_matrix_pairs"] += 1
            continue
        result["matrix_pairs"] += 1
        category = contract["pair_categories"][orders[a] * size + orders[b]]
        result["category_mass"][category] += 1
        # This exact training profile assigns zero only to unseen matrix pairs.
        result["unseen_matrix_pairs"] += category == 0
    return result


def rates(counters):
    def fraction(numerator, denominator):
        return {"numerator": numerator, "denominator": denominator} if denominator else None
    return {"frequent_letter_coverage": fraction(counters["frequent_letters"], counters["letters"]),
            "known_rare_letter_rate": fraction(counters["known_rare_letters"], counters["letters"]),
            "unknown_letter_rate": fraction(counters["unknown_letters"], counters["letters"]),
            "matrix_pair_coverage": fraction(counters["matrix_pairs"], counters["adjacent_letter_pairs"]),
            "unseen_matrix_pair_rate": fraction(counters["unseen_matrix_pairs"], counters["matrix_pairs"])}


def summarize(documents):
    """Micro counts and equally weighted defined document rates, exactly."""
    aggregate = {key: sum(item["counts"][key] for item in documents) for key in COUNTERS}
    aggregate["category_mass"] = [
        sum(item["counts"]["category_mass"][category] for item in documents)
        for category in range(4)
    ]
    macro = {}
    for name in rates(aggregate):
        values = [rates(item["counts"])[name] for item in documents]
        defined = [Fraction(value["numerator"], value["denominator"])
                   for value in values if value is not None]
        mean = sum(defined, Fraction()) / len(defined) if defined else None
        macro[name] = {
            "defined_documents": len(defined),
            "undefined_documents": len(values) - len(defined),
            "mean": ({"numerator": mean.numerator, "denominator": mean.denominator}
                     if mean is not None else None),
        }
    return {"source_count": len(documents), "aggregate_counts": aggregate,
            "aggregate_rates": rates(aggregate), "macro_rates": macro}


def size_strata(documents):
    """Disjoint complete-document byte ranges; never generate truncated variants."""
    result = []
    lower = 0
    for upper in (*SIZE_BOUNDS, None):
        selected = [item for item in documents
                    if item["counts"]["bytes"] >= lower
                    and (upper is None or item["counts"]["bytes"] < upper)]
        result.append({"minimum_bytes_inclusive": lower, "maximum_bytes_exclusive": upper,
                       **summarize(selected)})
        lower = upper
    return result


def evaluate(training, manifests, split):
    if split not in ("tuning", "validation"):
        raise ValueError("only tuning/validation diagnostics are allowed; independent is sealed")
    validate_training(training)
    if not manifests:
        raise ValueError("at least one evaluation manifest is required")
    contract = training["contract"]
    identity_splits = {"sha256": {}, "origin": {}}
    for source in contract["provenance"]["sources"]:
        for field in identity_splits:
            identity_splits[field][source[field]] = "training"
    checked = []
    seen_manifests = set()
    for manifest, root in manifests:
        validate_corpus(manifest, root)
        if manifest["content_hash"] in seen_manifests:
            raise ValueError("duplicate evaluation manifest")
        seen_manifests.add(manifest["content_hash"])
        # Audit every source, including unselected languages, variants and splits.
        for source in manifest["sources"]:
            for field, seen in identity_splits.items():
                identity = source[field]
                if identity in seen and seen[identity] != source["split"]:
                    raise ValueError(f"training/cross-manifest split leakage ({field})")
                seen[identity] = source["split"]
        checked.append((manifest, root))
    known_letters = {byte for d in training["documents"] for byte, n in enumerate(d["counts"]["symbols"]) if n}
    selected, seen_hashes, seen_origins = [], set(), set()
    for manifest, root in sorted(checked, key=lambda item: item[0]["content_hash"]):
        sources = {source["id"]: source for source in manifest["sources"]}
        for sample in sorted(manifest["samples"], key=lambda item: item["id"]):
            source = sources[sample["source_id"]]
            if source["language"] != contract["language"] or source["split"] != split:
                continue
            if sample["encoding"] != "cp1252" or sample["format"] != "text" or sample["boundary"] != "complete" or sample["byte_limit"] is not None:
                continue
            if source["sha256"] in seen_hashes or source["origin"] in seen_origins:
                raise ValueError("duplicate selected evaluation source hash/origin")
            seen_hashes.add(source["sha256"])
            seen_origins.add(source["origin"])
            observed = counts(safe_path(root, sample["path"]).read_bytes(), contract, known_letters)
            selected.append({"corpus_content_hash": manifest["content_hash"], "source": source,
                             "sample_id": sample["id"], "sample_sha256": sample["sha256"],
                             "encoder": sample["encoder"], "encoder_version": sample["encoder_version"],
                             "counts": observed, "rates": rates(observed)})
    if not selected:
        raise ValueError("no full complete cp1252 text documents for requested language/split")
    summary = summarize(selected)
    dependencies = training_dependencies()
    dependencies["models/experimental/sequence_evaluation.py"] = digest(Path(__file__).read_bytes())
    report = {"schema": VERSION, "deployment_status": "NOT_ENGINE_CALIBRATED",
              "metric": "fixed-table character/pair coverage; NOT encoding accuracy or confidence",
              "filter_profile": training["spec"]["filter"], "split": split,
              "language": contract["language"], "encoding": "cp1252", "runtime": runtime(),
              "training_artifact_hash": training["content_hash"], "model_contract_hash": contract["content_hash"],
              "evaluator_dependencies": dependencies, "evaluator_source_hash": digest(canonical(dependencies)),
              "audited_manifests": sorted(seen_manifests), "source_count": len(selected),
              "synthetic_only": all(item["source"]["kind"] == "synthetic" for item in selected),
              "sources": selected, **summary, "size_strata": size_strata(selected)}
    report["content_hash"] = digest(canonical(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("training", type=Path)
    parser.add_argument("split", choices=("tuning", "validation"))
    parser.add_argument("output", type=Path)
    parser.add_argument("manifests", type=Path, nargs="+")
    args = parser.parse_args()
    training = json.loads(args.training.read_text(encoding="utf-8"))
    manifests = [(json.loads(path.read_text(encoding="utf-8")), path.parent) for path in args.manifests]
    write_idempotent(args.output, canonical(evaluate(training, manifests, args.split)))


if __name__ == "__main__":
    main()
