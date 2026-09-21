# SPDX-License-Identifier: MIT
"""Bounded call-site counts, with uninstrumented and frozen-output comparisons."""

import argparse
import json
import subprocess
from pathlib import Path

from fixed_block_compare import canonical, content_hash, manifest_hash, sha, write_idempotent
from fixed_block_timing import FROZEN


def signature(record):
    value = f"{int(record['final_done'])}:{record['candidate_count']}"
    for candidate in record["candidates"]:
        for field in ("encoding", "language"):
            text = candidate[field]
            value += ":null:" if text is None else ":present:" + text.encode().hex()
        value += ":" + candidate["confidence_bits"]
    return value


def run(manifest_path, previous_path, plain, counted):
    manifest = json.loads(manifest_path.read_text())
    previous = json.loads(previous_path.read_text())
    if content_hash(previous) != FROZEN or previous.get("content_hash") != FROZEN:
        raise ValueError("requires frozen tuning pilot")
    if manifest_hash(manifest) != previous["manifest_hash"]:
        raise ValueError("manifest changed")
    samples = {sample["id"]: sample for sample in manifest["samples"]}
    binaries = {"plain": sha(plain), "counted": sha(counted)}
    documents = []
    root = manifest_path.parent.resolve()
    stages = ("construction", "first_document", "warm_document", "destruction")
    for old in previous["documents"]:
        sample = samples[old["sample_id"]]
        path = (root / sample["path"]).resolve()
        if sample["split"] != "tuning" or not path.is_relative_to(root):
            raise ValueError("requires tuning input inside corpus root")
        if path.stat().st_size > 4096 or sha(path) != old["sha256"]:
            raise ValueError("input changed or exceeds pilot")
        observations = {}
        for name, binary in (("plain", plain), ("counted", counted)):
            result = subprocess.run(
                [str(binary), str(path)], check=True, capture_output=True, text=True, timeout=10
            )
            observations[name] = json.loads(result.stdout)
        reference, observed = observations["plain"], observations["counted"]
        if (
            observed["byte_length"] != old["byte_length"]
            or reference["byte_length"] != old["byte_length"]
        ):
            raise ValueError("input length mismatch")
        for mode in observed["modes"]:
            if observed["modes"][mode]["snapshot"] != reference["modes"][mode]["snapshot"]:
                raise ValueError("instrumentation changed candidates")
            if any(value for stage in stages for value in reference["modes"][mode][stage].values()):
                raise ValueError("plain build unexpectedly counts allocations")
        expected = signature(old["blocks"]["1024"]["observations"]["0"])
        for mode in ("direct_fixed", "adapter_whole", "adapter_byte"):
            if observed["modes"][mode]["snapshot"] != expected:
                raise ValueError("result differs from frozen canonical feed")
        documents.append(dict(sample_id=sample["id"], sha256=old["sha256"], observation=observed))
    if binaries != {"plain": sha(plain), "counted": sha(counted)}:
        raise ValueError("binary changed during observation")
    result = dict(
        schema="fixed-block-allocation-calls-v1",
        pilot_hash=FROZEN,
        binaries=binaries,
        driver_hash=sha(Path(__file__)),
        documents=documents,
        metric="selected static-link API call counts, not physical allocations or memory",
        excluded=(
            "shared-library internals (including strdup), aligned/nothrow/sized allocation, mmap"
        ),
        self_test="eight paths checked by counted executable before input processing",
    )
    result["content_hash"] = content_hash(result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "previous", "plain", "counted", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    result = run(args.manifest, args.previous, args.plain.resolve(), args.counted.resolve())
    write_idempotent(args.output, canonical(result))
    print(result["content_hash"])
