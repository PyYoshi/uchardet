# SPDX-License-Identifier: MIT
"""Measure the frozen tuning pilot using native clocks, not Python elapsed time."""

import argparse
import json
import os
import platform
import statistics
import subprocess
from pathlib import Path

from fixed_block_compare import canonical, content_hash, manifest_hash, sha, write_idempotent

FROZEN = "d198e153f5167a561d5809f011717def074fb3ab3991d84fa0f438bad816c63d"
BLOCKS = (1, 7, 64, 1024)
CHUNKS = (0, 1, 64)


def run(manifest_path, report_path, binary):
    affinity = sorted(os.sched_getaffinity(0))
    if len(affinity) != 1:
        raise ValueError("pin the process to one CPU before measuring")
    report = json.loads(report_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    if content_hash(report) != FROZEN or report.get("content_hash") != FROZEN:
        raise ValueError("requires frozen tuning pilot")
    if manifest_hash(manifest) != report["manifest_hash"]:
        raise ValueError("manifest changed")
    samples = {s["id"]: s for s in manifest["samples"]}
    frozen_binary = sha(binary)
    root = manifest_path.parent.resolve()
    documents = []
    for old in report["documents"]:
        sample = samples[old["sample_id"]]
        path = (root / sample["path"]).resolve()
        if sample["split"] != "tuning" or not path.is_relative_to(root):
            raise ValueError("input not in tuning corpus")
        if path.stat().st_size > 4096 or sha(path) != old["sha256"]:
            raise ValueError("input changed or exceeds pilot")
        rows = []
        for block in BLOCKS:
            for chunk in CHUNKS:
                result = subprocess.run(
                    [str(binary), str(block), str(chunk), "100", "7", str(path)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                observation = json.loads(result.stdout)
                if observation["byte_length"] != old["byte_length"]:
                    raise ValueError("native input length mismatch")
                rows.append(observation)
        documents.append(
            dict(
                sample_id=sample["id"],
                sha256=old["sha256"],
                encoding=old["encoding"],
                observations=rows,
            )
        )
    if sha(binary) != frozen_binary:
        raise ValueError("binary changed during measurement")
    summary = {}
    for block in BLOCKS:
        for chunk in CHUNKS:
            totals = {mode: [0.0] * 7 for mode in ("whole", "direct_fixed", "adapter")}
            for document in documents:
                row = next(
                    r
                    for r in document["observations"]
                    if r["block"] == block and r["external_chunk"] == chunk
                )
                for mode in totals:
                    for i, value in enumerate(row["modes"][mode]["trial_mean_ns"]):
                        totals[mode][i] += value
            summary[f"{block}/{chunk}"] = {
                mode: statistics.median(values) for mode, values in totals.items()
            }
    result = dict(
        schema="fixed-block-warm-reuse-timing-v1",
        pilot_hash=FROZEN,
        binary_hash=frozen_binary,
        driver_hash=sha(Path(__file__)),
        uname=list(platform.uname()),
        affinity=affinity,
        clock="native steady_clock",
        iterations=100,
        repeats=7,
        warmup_per_mode=17,
        documents=documents,
        summary_sum_median_ns=summary,
        scope="sum of per-document trial means, not corpus-pass or request-tail latency",
    )
    result["content_hash"] = content_hash(result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "report", "binary", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    result = run(args.manifest, args.report, args.binary.resolve())
    write_idempotent(args.output, canonical(result))
    print(json.dumps(result["summary_sum_median_ns"], indent=2))
