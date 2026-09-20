# SPDX-License-Identifier: MIT
"""Compare fixed identity/filtered tables on the same native-filtered heldout input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import filtered_training as filtered
import sequence_evaluation as coverage
import sequence_training as identity
from model import canonical, digest, select, write_idempotent
from sequence_contract import content_hash

VERSION = "filtered-table-comparison-v1"


def counts(statistics, contract, known_letters):
    """Compute byte-order-independent coverage, not native sequence/confidence state."""
    identity.validate_counts(statistics)
    classes = identity.character_classes()
    orders, size = contract["byte_to_order"], contract["frequent_character_count"]
    result = dict.fromkeys(coverage.COUNTERS, 0)
    result["bytes"] = statistics["byte_count"]
    result["category_mass"] = [0] * 4
    for byte, number in enumerate(statistics["symbols"]):
        if classes[byte] != "letter":
            continue
        result["letters"] += number
        key = (
            "frequent_letters"
            if orders[byte] < size
            else "known_rare_letters"
            if byte in known_letters
            else "unknown_letters"
        )
        result[key] += number
    for a, b, number in statistics["pairs"]:
        if classes[a] != "letter" or classes[b] != "letter":
            continue
        result["adjacent_letter_pairs"] += number
        if orders[a] >= size or orders[b] >= size:
            result["outside_matrix_pairs"] += number
            continue
        result["matrix_pairs"] += number
        category = contract["pair_categories"][orders[a] * size + orders[b]]
        result["category_mass"][category] += number
        if category == 0:
            result["unseen_matrix_pairs"] += number
    return result


def known_letters(training):
    documents = training["documents"]
    observed = (
        document["counts"]
        if training["profile"] == identity.PROFILE
        else filtered.check_observation(document["observation"])[1]
        for document in documents
    )
    return {byte for document in observed for byte, n in enumerate(document["symbols"]) if n}


def strata(documents):
    result, lower = [], 0
    for upper in (*coverage.SIZE_BOUNDS, None):
        selected = [
            item
            for item in documents
            if item["raw_bytes"] >= lower and (upper is None or item["raw_bytes"] < upper)
        ]
        result.append(
            dict(
                minimum_raw_bytes_inclusive=lower,
                maximum_raw_bytes_exclusive=upper,
                **coverage.summarize(selected),
            )
        )
        lower = upper
    return result


def evaluate(identity_training, filtered_training, manifest, root, split, binary):
    if split not in ("tuning", "validation"):
        raise ValueError("only tuning/validation allowed; independent is sealed")
    identity.validate(identity_training)
    filtered.validate(filtered_training)
    baseline, proposed = identity_training["contract"], filtered_training["contract"]
    if baseline["language"] != proposed["language"] or canonical(
        baseline["provenance"]["sources"]
    ) != canonical(proposed["provenance"]["sources"]):
        raise ValueError("comparison requires the same training sources and language")
    if [d["sample_sha256"] for d in identity_training["documents"]] != [
        d["sample_sha256"] for d in filtered_training["documents"]
    ]:
        raise ValueError("comparison requires the same training sample bytes")
    trained = {
        field: {s[field] for s in baseline["provenance"]["sources"]}
        for field in ("sha256", "origin")
    }
    # Audit metadata before corpus validation (which reads every source).
    for source in manifest["sources"]:
        if source["split"] == "independent":
            raise ValueError("independent corpus must remain sealed")
        if source["split"] != "training" and any(
            source[field] in trained[field] for field in trained
        ):
            raise ValueError("training/evaluation source leakage")
    records = select(manifest, root, baseline["language"], split)
    if len({source["origin"] for source, _, _ in records}) != len(records):
        raise ValueError("duplicate evaluation source origin")
    if any(len(data) > filtered.SPEC["input_limit"] for _, _, data in records):
        raise ValueError("evaluation document exceeds 65536 byte diagnostic limit")
    binary = Path(binary).resolve(strict=True)
    fingerprint = digest(binary.read_bytes())
    if fingerprint != filtered_training["native_binary_sha256"]:
        raise ValueError("evaluation must use the training native binary")
    profiles = {"identity": identity_training, "filtered": filtered_training}
    letters = {name: known_letters(training) for name, training in profiles.items()}
    documents = {name: [] for name in profiles}
    observations = []
    for source, sample, data in records:
        observation = filtered.observe(binary, data)
        _, statistics = filtered.check_observation(observation)
        observations.append(
            dict(
                source=source,
                sample_sha256=sample["sha256"],
                sample_id=sample["id"],
                encoder=sample["encoder"],
                encoder_version=sample["encoder_version"],
                observation=observation,
            )
        )
        for name, training in profiles.items():
            counted = counts(statistics, training["contract"], letters[name])
            documents[name].append(
                dict(
                    source_id=source["id"],
                    raw_bytes=len(data),
                    counts=counted,
                    rates=coverage.rates(counted),
                )
            )
    if digest(binary.read_bytes()) != fingerprint:
        raise ValueError("native binary changed during evaluation")
    dependencies = filtered.dependencies()
    base = Path(__file__).resolve().parents[2]
    for name in (
        "models/experimental/filtered_evaluation.py",
        "models/experimental/sequence_evaluation.py",
    ):
        dependencies[name] = digest((base / name).read_bytes())
    result = dict(
        schema=VERSION,
        metric="same-filter fixed-table coverage; NOT accuracy/confidence",
        deployment_status="NOT_ENGINE_CALIBRATED",
        split=split,
        language=baseline["language"],
        encoding="cp1252",
        native_binary_sha256=fingerprint,
        filter_spec=filtered.SPEC.copy(),
        corpus_content_hash=manifest["content_hash"],
        runtime=identity.runtime(),
        dependencies=dependencies,
        observations=observations,
        synthetic_only=all(source["kind"] == "synthetic" for source, _, _ in records),
        profiles={
            name: dict(
                training_artifact_hash=training["content_hash"],
                contract_hash=training["contract"]["content_hash"],
                documents=documents[name],
                **coverage.summarize(documents[name]),
                raw_size_strata=strata(documents[name]),
            )
            for name, training in profiles.items()
        },
    )
    result["content_hash"] = content_hash(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identity", type=Path)
    parser.add_argument("filtered", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("split", choices=("tuning", "validation"))
    parser.add_argument("binary", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    def load(path):
        return json.loads(path.read_text(encoding="utf-8"))

    report = evaluate(
        load(args.identity),
        load(args.filtered),
        load(args.manifest),
        args.manifest.parent,
        args.split,
        args.binary,
    )
    write_idempotent(args.output, canonical(report))


if __name__ == "__main__":
    main()
