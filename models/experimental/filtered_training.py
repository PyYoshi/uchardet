# SPDX-License-Identifier: MIT
"""Experimental native-filter training; not calibrated for detector deployment."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import sequence_training as identity
from model import canonical, digest, select, write_idempotent
from sequence_contract import SCHEMA, content_hash
from sequence_contract import validate as validate_contract

PROFILE = "cp1252-native-filter-sequence-training-v1"
SPEC = dict(
    identity.SPEC,
    filter="FilterWithoutEnglishLettersToBuffer",
    observation="sbcs-filter-profile-v1",
    input_limit=65536,
    feed_policy="whole-document",
    chunk_size=0,
)


def dependencies():
    result = identity.dependencies()
    base = Path(__file__).resolve().parents[2]
    for name in (
        "models/experimental/filtered_training.py",
        "benchmark/uchardet-filter-profile.cpp",
        "src/nsCharSetProber.cpp",
        "src/nsCharSetProber.h",
    ):
        result[name] = digest((base / name).read_bytes())
    return result


def counts(statistics):
    if set(statistics) != {"bytes", "symbols", "pairs"}:
        raise ValueError("unexpected filter statistics fields")
    result = dict(
        byte_count=statistics["bytes"], symbols=statistics["symbols"], pairs=statistics["pairs"]
    )
    identity.validate_counts(result)
    return result


def check_observation(observation):
    if (
        set(observation) != {"schema", "chunk_size", "raw", "filtered", "calls"}
        or observation["schema"] != SPEC["observation"]
        or type(observation["chunk_size"]) is not int
        or observation["chunk_size"] != 0
    ):
        raise ValueError("expected whole-document native filter observation")
    raw, filtered = counts(observation["raw"]), counts(observation["filtered"])
    size, retained = raw["byte_count"], filtered["byte_count"]
    if size > SPEC["input_limit"] or retained > size:
        raise ValueError("filter input/output exceeds limit")
    expected = [[size, retained]] if size else []
    # canonical comparison rejects booleans masquerading as integer lengths.
    if canonical(observation["calls"]) != canonical(expected):
        raise ValueError("filter calls differ from whole-document policy")
    return raw, filtered


def observe(binary, data):
    if len(data) > SPEC["input_limit"]:
        raise ValueError("training document exceeds 65536 byte diagnostic limit")
    # Pass exactly the bytes validated by corpus selection, not a reopened corpus path.
    with tempfile.TemporaryDirectory(prefix="uchardet-filter-training-") as directory:
        path = Path(directory) / "input.bin"
        path.write_bytes(data)
        completed = subprocess.run(
            [str(binary), "0", str(path)], check=True, capture_output=True, timeout=10
        )
    observation = json.loads(completed.stdout)
    raw, _ = check_observation(observation)
    if raw != identity.count_document(data):
        raise ValueError("native raw statistics differ from validated input bytes")
    return observation


def make_contract(documents, language, corpus_hash, dep, binary_hash):
    fields, audit = identity.derive(
        [{"counts": check_observation(document["observation"])[1]} for document in documents]
    )
    contract = dict(
        schema=SCHEMA,
        encoding="cp1252",
        language=language,
        **fields,
        keep_english_letters=False,
        generated_model_license="UNDETERMINED",
        generation_parameters={
            "character_order": PROFILE + ":letters-count-desc-byte-asc",
            "pair_categories": PROFILE + ":95-99-frequency-ties",
            "filter": SPEC["filter"],
            "typical_positive_ratio": SPEC["ratio"],
            "document_boundaries": SPEC["document_boundaries"],
            "feed_policy": SPEC["feed_policy"],
            "native_binary_sha256": binary_hash,
        },
        provenance={
            "generator_version": PROFILE,
            "generator_license": "MIT",
            "generator_source_sha256": digest(canonical(dep)),
            "corpus_content_hash": corpus_hash,
            "sources": [document["source"] for document in documents],
        },
    )
    contract["content_hash"] = content_hash(contract)
    validate_contract(contract)
    return contract, audit


def train(manifest, root, language, binary):
    # Corpus validation reads all sources: refuse sealed independent data first.
    if any(source["split"] == "independent" for source in manifest["sources"]):
        raise ValueError("independent corpus must remain sealed")
    records = select(manifest, root, language, "training")
    if any(len(data) > SPEC["input_limit"] for _, _, data in records):
        raise ValueError("training document exceeds 65536 byte diagnostic limit")
    binary = Path(binary).resolve(strict=True)
    binary_hash = digest(binary.read_bytes())
    documents = [
        dict(
            source=source,
            sample_sha256=sample["sha256"],
            encoder=sample["encoder"],
            encoder_version=sample["encoder_version"],
            observation=observe(binary, data),
        )
        for source, sample, data in records
    ]
    if digest(binary.read_bytes()) != binary_hash:
        raise ValueError("native binary changed during training")
    dep = dependencies()
    contract, audit = make_contract(documents, language, manifest["content_hash"], dep, binary_hash)
    artifact = dict(
        profile=PROFILE,
        spec=SPEC.copy(),
        deployment_status="NOT_ENGINE_CALIBRATED",
        runtime=identity.runtime(),
        dependencies=dep,
        native_binary_sha256=binary_hash,
        documents=documents,
        contract=contract,
        audit=audit,
    )
    artifact["content_hash"] = content_hash(artifact)
    validate(artifact)
    return artifact


def validate(artifact):
    if artifact.get("content_hash") != content_hash(artifact):
        raise ValueError("filtered training artifact hash mismatch")
    if (
        artifact.get("profile") != PROFILE
        or canonical(artifact.get("spec")) != canonical(SPEC)
        or artifact.get("deployment_status") != "NOT_ENGINE_CALIBRATED"
    ):
        raise ValueError("unsupported filtered training profile/status")
    if (
        artifact.get("dependencies") != dependencies()
        or artifact.get("runtime") != identity.runtime()
    ):
        raise ValueError("generator/runtime revision mismatch")
    binary_hash = artifact["native_binary_sha256"]
    if (
        not isinstance(binary_hash, str)
        or len(binary_hash) != 64
        or any(c not in "0123456789abcdef" for c in binary_hash)
    ):
        raise ValueError("invalid native binary hash")
    documents, contract = artifact["documents"], artifact["contract"]
    if not isinstance(documents, list) or not documents:
        raise ValueError("missing document audit")
    if [d["source"]["id"] for d in documents] != sorted(d["source"]["id"] for d in documents):
        raise ValueError("noncanonical document order")
    for document in documents:
        if document["source"]["language"] != contract["language"]:
            raise ValueError("training language mismatch")
        value = document["sample_sha256"]
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise ValueError("invalid sample hash")
        if any(
            not isinstance(document[name], str) or not document[name]
            for name in ("encoder", "encoder_version")
        ):
            raise ValueError("missing encoder metadata")
    expected, audit = make_contract(
        documents,
        contract["language"],
        contract["provenance"]["corpus_content_hash"],
        artifact["dependencies"],
        binary_hash,
    )
    if canonical(expected) != canonical(contract) or canonical(audit) != canonical(
        artifact["audit"]
    ):
        raise ValueError("contract/audit differs from recomputed filtered counts")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    training = commands.add_parser("train")
    training.add_argument("manifest", type=Path)
    training.add_argument("language")
    training.add_argument("binary", type=Path)
    training.add_argument("output", type=Path)
    checking = commands.add_parser("validate")
    checking.add_argument("artifact", type=Path)
    checking.add_argument("--manifest", type=Path)
    checking.add_argument("--binary", type=Path)
    args = parser.parse_args()
    if args.command == "train":
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        write_idempotent(
            args.output,
            canonical(train(manifest, args.manifest.parent, args.language, args.binary)),
        )
    else:
        if bool(args.manifest) != bool(args.binary):
            parser.error("--manifest and --binary must be supplied together")
        artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
        validate(artifact)
        if args.manifest:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            if (
                train(manifest, args.manifest.parent, artifact["contract"]["language"], args.binary)
                != artifact
            ):
                raise ValueError("artifact differs from regenerated corpus/native observation")


if __name__ == "__main__":
    main()
