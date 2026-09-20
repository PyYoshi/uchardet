# SPDX-License-Identifier: MIT
"""Observe selected static-link allocation call sites during warmed single-prober reuse."""

import argparse
import json
import tempfile
from pathlib import Path

import native_comparison
import sequence_probe
from model import canonical, digest, write_idempotent
from sequence_contract import content_hash


def run(identity, filtered, manifest, root, split, library, compiler="c++"):
    records = native_comparison.select_records(
        identity, filtered, manifest, root, split
    )
    library = Path(library).resolve(strict=True)
    library_hash = digest(library.read_bytes())
    profiles = {}
    with tempfile.TemporaryDirectory(prefix="uchardet-allocations-") as temporary:
        for name, training in (
            ("legacy", None),
            ("identity", identity),
            ("filtered", filtered),
        ):
            builds = []
            for enabled in (False, True):
                directory = Path(temporary) / f"{name}-{enabled}"
                directory.mkdir()
                build = (
                    sequence_probe.build_reference(
                        library, directory, compiler, allocations=enabled
                    )
                    if training is None
                    else sequence_probe.build(
                        training["contract"],
                        library,
                        directory,
                        compiler,
                        allocations=enabled,
                    )
                )
                if build[1]["static_library_sha256"] != library_hash:
                    raise ValueError("library changed between builds")
                builds.append(build)
            observations = []
            for source, sample, data in records:
                plain = sequence_probe.observe(builds[0][0], data)
                counted = sequence_probe.observe(builds[1][0], data)
                calls = counted.pop("allocation_calls")
                if counted != plain:
                    raise ValueError("instrumented observation differs from reference")
                observations.append(
                    dict(
                        source=source,
                        sample_sha256=sample["sha256"],
                        byte_length=len(data),
                        calls=calls,
                        observation=plain,
                    )
                )
            profiles[name] = dict(
                training_artifact_hash=training["content_hash"] if training else None,
                baseline_provenance=builds[0][1],
                counted_provenance=builds[1][1],
                observations=observations,
            )
    if digest(library.read_bytes()) != library_hash:
        raise ValueError("library changed during observation")
    report = dict(
        schema="native-model-allocation-calls-v1",
        corpus_content_hash=manifest["content_hash"],
        split=split,
        warmup_iterations=128,
        observed_iterations=1,
        scope="static-link calls to malloc/calloc/realloc/free and throwing unaligned new/delete",
        excluded="shared-library internals, aligned/nothrow/sized/custom allocators, mmap, setup, I/O",
        metric="API call counts, not physical allocations, live bytes, peak memory or latency",
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
    parser.add_argument(
        "--split", choices=("tuning", "validation"), default="validation"
    )
    parser.add_argument("--cxx", default="c++")
    args = parser.parse_args()

    def load(path):
        return json.loads(path.read_text(encoding="utf-8"))

    result = run(
        load(args.identity),
        load(args.filtered),
        load(args.manifest),
        args.manifest.parent,
        args.split,
        args.library,
        args.cxx,
    )
    write_idempotent(args.output, canonical(result))


if __name__ == "__main__":
    main()
