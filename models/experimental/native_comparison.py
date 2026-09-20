# SPDX-License-Identifier: MIT
"""Compare legacy and frozen generated French models; not whole-detector accuracy."""

from __future__ import annotations

import argparse
import json
import math
import struct
import tempfile
from pathlib import Path

import filtered_training
import sequence_probe
import sequence_training
from model import canonical, digest, select, write_idempotent
from sequence_contract import content_hash


def select_records(identity, filtered, manifest, root, split):
    if split not in ("tuning", "validation"):
        raise ValueError("independent is sealed; choose tuning/validation")
    sequence_training.validate(identity)
    filtered_training.validate(filtered)
    if any(t["contract"]["language"] != "fr" for t in (identity, filtered)):
        raise ValueError("reference comparison supports French only")
    first, second = (t["contract"]["provenance"]["sources"] for t in (identity, filtered))
    if canonical(first) != canonical(second):
        raise ValueError("generated profiles must use the same training sources")
    if [d["sample_sha256"] for d in identity["documents"]] != [
        d["sample_sha256"] for d in filtered["documents"]
    ]:
        raise ValueError("generated profiles must use the same training sample bytes")
    trained = {field: {s[field] for s in first} for field in ("sha256", "origin")}
    for source in manifest["sources"]:
        if source["split"] == "independent":
            raise ValueError("independent source must remain sealed")
        if source["split"] != "training" and any(source[f] in trained[f] for f in trained):
            raise ValueError("training/evaluation source leakage")
    records = select(manifest, root, "fr", split)
    if len({s["origin"] for s, _, _ in records}) != len(records):
        raise ValueError("duplicate evaluation source origin")
    if any(len(data) > 65536 for _, _, data in records):
        raise ValueError("evaluation document exceeds 65536 byte limit")
    return records


def summarize(documents):
    states = {"detecting": 0, "found": 0, "rejected": 0}
    names = tuple(states)
    finite, nonfinite = [], 0
    for document in documents:
        snapshot = document["observation"]["snapshot"]
        state = snapshot["state"]
        if type(state) is not int or not 0 <= state <= 2:
            raise ValueError("invalid prober state")
        states[names[state]] += 1
        value = struct.unpack("!f", bytes.fromhex(snapshot["confidence_bits"]))[0]
        if math.isfinite(value):
            finite.append(value)
        else:
            nonfinite += 1
    return dict(
        documents=len(documents),
        states=states,
        finite_confidences=len(finite),
        nonfinite_confidences=nonfinite,
        confidence_min=min(finite) if finite else None,
        confidence_max=max(finite) if finite else None,
        below_zero=sum(value < 0 for value in finite),
        above_one=sum(value > 1 for value in finite),
    )


def compare(identity, filtered, manifest, root, split, library, compiler="c++"):
    records = select_records(identity, filtered, manifest, root, split)
    library = Path(library).resolve(strict=True)
    library_hash = digest(library.read_bytes())
    profiles, lengths = {}, {}
    for name, training in (("legacy", None), ("identity", identity), ("filtered", filtered)):
        with tempfile.TemporaryDirectory(prefix="uchardet-model-comparison-") as directory:
            if training is None:
                binary, provenance = sequence_probe.build_reference(library, directory, compiler)
            else:
                binary, provenance = sequence_probe.build(
                    training["contract"], library, directory, compiler
                )
            if provenance["static_library_sha256"] != library_hash:
                raise ValueError("static library differs between models")
            documents = []
            for source, sample, data in records:
                observed = sequence_probe.observe(binary, data)
                current = (observed["raw_bytes"], observed["filtered_bytes"])
                if source["id"] in lengths and current != lengths[source["id"]]:
                    raise ValueError("filter lengths differ between models")
                lengths[source["id"]] = current
                documents.append(
                    dict(
                        source=source,
                        sample_sha256=sample["sha256"],
                        sample_id=sample["id"],
                        encoder=sample["encoder"],
                        encoder_version=sample["encoder_version"],
                        observation=observed,
                    )
                )
        profiles[name] = dict(
            training_artifact_hash=training["content_hash"] if training else None,
            provenance=provenance,
            documents=documents,
            summary=summarize(documents),
        )
    if digest(library.read_bytes()) != library_hash:
        raise ValueError("static library changed during comparison")
    report = dict(
        schema="native-french-model-comparison-v1",
        deployment_status="NOT_ENGINE_CALIBRATED",
        metric="single-prober counters/state/internal confidence; NOT encoding accuracy",
        corpus_content_hash=manifest["content_hash"],
        split=split,
        legacy_training_overlap="UNKNOWN",
        runtime=sequence_training.runtime(),
        driver_source_sha256=digest(Path(__file__).read_bytes()),
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
