# SPDX-License-Identifier: MIT
"""Pinned-CPU warmed native single-model timing; no Python or file I/O in measured interval."""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import tempfile
from pathlib import Path

import native_comparison
import sequence_probe
from model import canonical, digest, write_idempotent
from sequence_contract import content_hash

NAMES = ("legacy", "identity", "filtered")


def summary(trials, iterations):
    if not trials or any(type(value) is not int or value <= 0 for value in trials):
        raise ValueError("positive integer trial times required")
    if type(iterations) is not int or not 1 <= iterations <= 1000000:
        raise ValueError("invalid iteration count")
    values = sorted(value / iterations for value in trials)
    return dict(
        median_ns_per_iteration=statistics.median(values),
        minimum_ns_per_iteration=values[0],
        maximum_ns_per_iteration=values[-1],
        # Nearest-rank p95 of trial averages, NOT per-request tail latency.
        p95_trial_mean_ns_per_iteration=values[(95 * len(values) + 99) // 100 - 1],
    )


def affinity():
    if not hasattr(os, "sched_getaffinity"):
        raise ValueError("this benchmark runner requires Linux CPU affinity")
    cpus = sorted(os.sched_getaffinity(0))
    if len(cpus) != 1:
        raise ValueError("pin the process to one allowed CPU with taskset")
    return cpus


def cpu_environment(cpu):
    info = {}
    for block in Path("/proc/cpuinfo").read_text(encoding="utf-8").split("\n\n"):
        fields = dict(line.split(":", 1) for line in block.splitlines() if ":" in line)
        fields = {key.strip(): value.strip() for key, value in fields.items()}
        if fields.get("processor") == str(cpu):
            info["model_name"] = fields.get("model name")
            break
    governor = Path(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor")
    info["scaling_governor"] = governor.read_text().strip() if governor.is_file() else None
    return info


def run(
    identity, filtered, manifest, root, split, library, iterations=20000, repeats=7, compiler="c++"
):
    if type(iterations) is not int or not 1 <= iterations <= 1000000:
        raise ValueError("iterations must be in [1, 1000000]")
    if type(repeats) is not int or not 3 <= repeats <= 31:
        raise ValueError("repeats must be in [3, 31]")
    cpus = affinity()
    cpu_info = cpu_environment(cpus[0])
    records = native_comparison.select_records(identity, filtered, manifest, root, split)
    library = Path(library).resolve(strict=True)
    library_hash = digest(library.read_bytes())
    profiles, binaries, baselines = {}, {}, {}
    with tempfile.TemporaryDirectory(prefix="uchardet-model-timing-") as temporary:
        for name, training in (("legacy", None), ("identity", identity), ("filtered", filtered)):
            directory = Path(temporary) / name
            directory.mkdir()
            binary, provenance = (
                sequence_probe.build_reference(library, directory, compiler)
                if training is None
                else sequence_probe.build(training["contract"], library, directory, compiler)
            )
            if provenance["static_library_sha256"] != library_hash:
                raise ValueError("library differs between model builds")
            binaries[name] = binary
            baselines[name] = {
                source["id"]: sequence_probe.observe(binary, data) for source, _, data in records
            }
            profiles[name] = dict(
                provenance=provenance,
                training_artifact_hash=training["content_hash"] if training else None,
                sources={
                    source["id"]: dict(
                        source=source,
                        sample_sha256=sample["sha256"],
                        byte_length=len(data),
                        elapsed_ns=[],
                        trial_resources=[],
                    )
                    for source, sample, data in records
                },
            )
        # Build all models before timing. Rotate their order for every source/repetition.
        for repeat in range(repeats):
            for index, (source, _, data) in enumerate(records):
                offset = (repeat + index) % len(NAMES)
                for name in (*NAMES[offset:], *NAMES[:offset]):
                    observed = sequence_probe.observe(binaries[name], data, iterations)
                    timing = observed.pop("benchmark")
                    if observed != baselines[name][source["id"]]:
                        raise ValueError("timed run differs from untimed observation")
                    if timing.get("resources") is None:
                        raise ValueError("Linux timing requires native resource observation")
                    profiles[name]["sources"][source["id"]]["elapsed_ns"].append(
                        timing["elapsed_ns"]
                    )
                    profiles[name]["sources"][source["id"]]["trial_resources"].append(
                        timing["resources"]
                    )
    if affinity() != cpus or digest(library.read_bytes()) != library_hash:
        raise ValueError("affinity/library changed during timing")
    for profile in profiles.values():
        for source in profile["sources"].values():
            source["summary"] = summary(source["elapsed_ns"], iterations)
        # Sum independent hot-document trials; do not present this as an interleaved corpus pass.
        totals = [
            sum(source["elapsed_ns"][i] for source in profile["sources"].values())
            for i in range(repeats)
        ]
        profile["summed_document_trial_summary"] = summary(totals, iterations)
    report = dict(
        schema="native-model-timing-v2",
        corpus_content_hash=manifest["content_hash"],
        split=split,
        scope="reused single prober: reset + filter + feed + confidence + checksum",
        excluded="input I/O, allocation of input/scratch/prober, compilation, Python, output",
        iterations=iterations,
        repeats=repeats,
        warmup_iterations=128,
        clock="C++ steady_clock; nanoseconds",
        resource_scope="Linux RUSAGE_SELF deltas around wall interval; single-thread process",
        resource_precision="CPU timeval microseconds converted to ns; not nanosecond resolution",
        cpu_affinity=cpus,
        aggregate_policy=(
            "sum of independent warmed same-document trial means; not interleaved corpus"
        ),
        environment=dict(
            system=platform.system(),
            release=platform.release(),
            machine=platform.machine(),
            cpu_before=cpu_info,
            cpu_after=cpu_environment(cpus[0]),
        ),
        driver_dependencies={
            path.name: digest(path.read_bytes())
            for path in (Path(__file__), Path(native_comparison.__file__))
        },
        profiles=profiles,
    )
    report["content_hash"] = content_hash(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("identity", "filtered", "manifest", "library", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--split", choices=("tuning", "validation"), default="validation")
    parser.add_argument("--iterations", type=int, default=20000)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--cxx", default="c++")
    args = parser.parse_args()

    def load(path):
        return json.loads(path.read_text(encoding="utf-8"))

    report = run(
        load(args.identity),
        load(args.filtered),
        load(args.manifest),
        args.manifest.parent,
        args.split,
        args.library,
        args.iterations,
        args.repeats,
        args.cxx,
    )
    write_idempotent(args.output, canonical(report))


if __name__ == "__main__":
    main()
