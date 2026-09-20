# SPDX-License-Identifier: MIT
"""Small paired-corpus candidate observations; no default model replacement."""
import argparse
import codecs
import json
from pathlib import Path

import engine_probe
import paired_controls
from model import canonical, digest, safe_path, write_idempotent
from sequence_contract import content_hash, emit_cpp


def score(record, data, encoding, language):
    expected = codecs.lookup(encoding).name
    candidates = record["candidates"]
    names = []
    for candidate in candidates:
        try:
            names.append(codecs.lookup(candidate["encoding"]).name)
        except (LookupError, TypeError):
            names.append(None)
    ranks = [i + 1 for i, name in enumerate(names) if name == expected]
    status = "no_candidate"
    if candidates:
        status = "unknown_codec"
        if names[0] is not None:
            try:
                decoded = data.decode(names[0], errors="strict")
                status = "equal" if decoded == data.decode(expected, errors="strict") else "different"
            except UnicodeError:
                status = "decode_error"
    return dict(expected_codec=expected, top1_exact_codec=bool(names and names[0] == expected),
                top1_decode_status=status, expected_candidate_ranks=ranks,
                top1_language_match=bool(candidates and candidates[0]["language"] == language))


def verified_build(directory, training):
    directory = Path(directory).resolve(strict=True)
    provenance = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    if provenance["mode"] != "generated" or provenance["contract_hash"] != training["contract"]["content_hash"]:
        raise ValueError("build does not match frozen training contract")
    header = (directory / "model.hpp").read_bytes()
    if header != emit_cpp(training["contract"]) or digest(header) != provenance["model_header_sha256"]:
        raise ValueError("generated build header mismatch")
    for path, sha in provenance["dependencies"].items():
        if digest(safe_path(engine_probe.BASE, path).read_bytes()) != sha:
            raise ValueError("build source revision mismatch")
    binaries = {}
    for name in ("uchardet-conformance", "uchardet-conformance-experimental"):
        binary = directory / "build/benchmark" / name
        if digest(binary.read_bytes()) != provenance["binaries"][name]:
            raise ValueError("build executable hash mismatch")
        binaries[name] = binary
    return binaries, provenance


def compare(identity, filtered, manifest, root, split, identity_build, filtered_build):
    records, pairs = paired_controls.select_pairs(identity, filtered, manifest, root, split)
    if any(len(data) > engine_probe.LIMIT for _, _, data in records):
        raise ValueError("paired full-engine evaluation requires every input <=4096 bytes")
    inputs = (("identity", identity, identity_build), ("filtered", filtered, filtered_build))
    builds = {name: verified_build(directory, training) for name, training, directory in inputs}
    documents = []
    for source, sample, data in records:
        observed = {}
        for name, _, _ in inputs:
            binaries, _ = builds[name]
            baseline = engine_probe.observe(binaries["uchardet-conformance"], data)
            if "legacy" in observed and baseline != observed["legacy"]:
                raise ValueError("normal target differs between generated builds")
            observed["legacy"] = baseline
            observed[name] = engine_probe.observe(binaries["uchardet-conformance-experimental"], data)
        documents.append(dict(source=source, sample_id=sample["id"],
                              sample_sha256=sample["sha256"], sample_encoding=sample["encoding"],
                              byte_length=len(data), observations=observed,
                              scores={name: score(value, data, sample["encoding"], source["language"])
                                      for name, value in observed.items()}))
    for name, training, directory in inputs:
        _, final = verified_build(directory, training)
        if final != builds[name][1]:
            raise ValueError("build changed during evaluation")
    summary = {}
    for encoding in ("cp1252", "utf-8"):
        selected = [row for row in documents if row["sample_encoding"] == encoding]
        summary[encoding] = {}
        for name in ("legacy", "identity", "filtered"):
            summary[encoding][name] = dict(
                samples=len(selected), exact_codec=sum(d["scores"][name]["top1_exact_codec"] for d in selected),
                language_match=sum(d["scores"][name]["top1_language_match"] for d in selected),
                expected_candidate_present=sum(bool(d["scores"][name]["expected_candidate_ranks"]) for d in selected),
                decode_status={status: sum(d["scores"][name]["top1_decode_status"] == status for d in selected)
                               for status in ("equal", "different", "decode_error", "unknown_codec", "no_candidate")},
            )
    result = dict(schema="small-paired-engine-comparison-v1", corpus_content_hash=manifest["content_hash"],
                  split=split, scope="one French cp1252 slot; all other engine/model code unchanged",
                  input_limit=engine_probe.LIMIT, feed="whole/fresh", pairs=pairs, documents=documents,
                  summary=summary, builds={name: provenance for name, (_, provenance) in builds.items()},
                  training_hashes={"identity": identity["content_hash"], "filtered": filtered["content_hash"]},
                  legacy_training_overlap="UNKNOWN", compatible_superset_metric="NOT_EVALUATED",
                  driver_dependencies={p.name: digest(p.read_bytes()) for p in
                                       (Path(__file__), Path(engine_probe.__file__), Path(paired_controls.__file__))})
    result["content_hash"] = content_hash(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("identity", "filtered", "manifest", "identity_build", "filtered_build", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--split", choices=("tuning", "validation"), default="validation")
    args = parser.parse_args()
    def load(path):
        return json.loads(path.read_text(encoding="utf-8"))
    result = compare(load(args.identity), load(args.filtered), load(args.manifest), args.manifest.parent,
                     args.split, args.identity_build, args.filtered_build)
    write_idempotent(args.output, canonical(result))


if __name__ == "__main__":
    main()
