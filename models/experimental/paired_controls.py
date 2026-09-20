# SPDX-License-Identifier: MIT
"""Same-source cp1252/UTF-8 controls for a single French prober, not detector accuracy."""

from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path

import native_comparison
import sequence_training
from model import canonical, digest, safe_path, write_idempotent
from sequence_contract import content_hash


def select_pairs(identity, filtered, manifest, root, split):
    # Includes full corpus verification and metadata-only independent/leakage refusal.
    positives = native_comparison.select_records(identity, filtered, manifest, root, split)
    candidates = {}
    for sample in manifest["samples"]:
        if (
            sample["encoding"] == "utf-8"
            and sample["format"] == "text"
            and sample["boundary"] == "complete"
            and sample["byte_limit"] is None
        ):
            candidates.setdefault(sample["source_id"], []).append(sample)
    records, pairs = [], []
    for source, positive, data in positives:
        matches = candidates.get(source["id"], [])
        if len(matches) != 1:
            raise ValueError(
                "each selected cp1252 document needs exactly one full UTF-8 counterpart"
            )
        control = matches[0]
        other = safe_path(root, control["path"]).read_bytes()
        if len(other) > 65536:
            raise ValueError("UTF-8 control exceeds 65536 byte limit")
        if data.decode("cp1252", errors="strict") != other.decode("utf-8", errors="strict"):
            raise ValueError("paired encodings differ in decoded text")
        try:
            other.decode("cp1252", errors="strict")
            decodable = True
        except UnicodeDecodeError:
            decodable = False
        records.extend(((source, positive, data), (source, control, other)))
        pairs.append(
            dict(
                source_id=source["id"],
                positive_sample=positive["id"],
                control_sample=control["id"],
                bytes_identical=data == other,
                control_cp1252_decodable=decodable,
            )
        )
    return records, pairs


def separation(documents, pairs):
    indexed = {document["sample_id"]: document for document in documents}
    result = dict(
        total_pairs=len(pairs),
        byte_identical_pairs=0,
        finite_distinct_pairs=0,
        nonfinite_distinct_pairs=0,
        positive_higher=0,
        equal=0,
        control_higher=0,
    )
    for pair in pairs:
        if pair["bytes_identical"]:
            result["byte_identical_pairs"] += 1
            continue
        values = [
            struct.unpack(
                "!f",
                bytes.fromhex(indexed[pair[field]]["observation"]["snapshot"]["confidence_bits"]),
            )[0]
            for field in ("positive_sample", "control_sample")
        ]
        if not all(math.isfinite(value) for value in values):
            result["nonfinite_distinct_pairs"] += 1
            continue
        result["finite_distinct_pairs"] += 1
        key = (
            "positive_higher"
            if values[0] > values[1]
            else "control_higher"
            if values[0] < values[1]
            else "equal"
        )
        result[key] += 1
    return result


def compare(identity, filtered, manifest, root, split, library, compiler="c++"):
    records, pairs = select_pairs(identity, filtered, manifest, root, split)
    profiles = native_comparison.observe_models(identity, filtered, records, library, compiler)
    for profile in profiles.values():
        documents = profile["documents"]
        profile["summary"] = {
            encoding: native_comparison.summarize(
                [document for document in documents if document["sample_encoding"] == encoding]
            )
            for encoding in ("cp1252", "utf-8")
        }
        profile["paired_separation"] = separation(documents, pairs)
        profile["control_decodability_strata"] = {
            name: separation(
                documents, [pair for pair in pairs if pair["control_cp1252_decodable"] == value]
            )
            for name, value in (("cp1252_decodable", True), ("cp1252_undecodable", False))
        }
        for encoding, summary in profile["summary"].items():
            summary["stopped_before_filtered_end"] = sum(
                document["observation"]["snapshot"]["total_characters"]
                < document["observation"]["filtered_bytes"]
                for document in documents
                if document["sample_encoding"] == encoding
            )
    dependencies = {
        path.name: digest(path.read_bytes())
        for path in (Path(__file__), Path(native_comparison.__file__))
    }
    report = dict(
        schema="paired-french-encoding-controls-v1",
        deployment_status="NOT_ENGINE_CALIBRATED",
        metric="same-text prober response contrast; NOT false-positive rate or encoding accuracy",
        corpus_content_hash=manifest["content_hash"],
        split=split,
        pairs=pairs,
        legacy_training_overlap="UNKNOWN",
        runtime=sequence_training.runtime(),
        driver_dependencies=dependencies,
        profiles=profiles,
    )
    report["content_hash"] = content_hash(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identity", type=Path)
    parser.add_argument("filtered", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("split", choices=("tuning", "validation"))
    parser.add_argument("library", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cxx", default="c++")
    args = parser.parse_args()

    def load(path):
        return json.loads(path.read_text(encoding="utf-8"))

    report = compare(
        load(args.identity),
        load(args.filtered),
        load(args.manifest),
        args.manifest.parent,
        args.split,
        args.library,
        args.cxx,
    )
    write_idempotent(args.output, canonical(report))


if __name__ == "__main__":
    main()
