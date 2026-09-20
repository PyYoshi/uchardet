# SPDX-License-Identifier: MIT
"""Build/run an opt-in probe using a validated model and a trusted native static library."""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from model import canonical, digest, write_idempotent
from sequence_contract import content_hash, emit_cpp, validate

FLAGS = ["-std=c++11", "-O2", "-Wall", "-Wextra", "-Wpedantic"]


def build(contract, library, directory, compiler="c++", *, allocations=False):
    validate(contract)
    return _build(
        emit_cpp(contract),
        {"contract_hash": contract["content_hash"]},
        library,
        directory,
        compiler,
        allocations=allocations,
    )


def build_reference(library, directory, compiler="c++", *, allocations=False):
    """Use the linked legacy model without copying its tables or claiming new provenance."""
    header = (
        '#pragma once\n#include "nsSBCharSetProber.h"\n'
        '#include "nsSBCharSetProber-generated.h"\n'
        "namespace uchardet_sequence_pilot {\n"
        "static const SequenceModel& model = Windows_1252FrenchModel;\n}\n"
    ).encode()
    source = Path(__file__).resolve().parents[2] / "src/LangModels/LangFrenchModel.cpp"
    return _build(
        header,
        {
            "reference_symbol": "Windows_1252FrenchModel",
            "reference_source_sha256": digest(source.read_bytes()),
            "training_provenance": "LEGACY_NOT_VERIFIED",
        },
        library,
        directory,
        compiler,
        allocations=allocations,
    )


def _build(header, model_metadata, library, directory, compiler, *, allocations=False):
    if allocations and (sys.platform != "linux" or struct.calcsize("P") != 8):
        raise ValueError("allocation instrumentation requires 64-bit Linux/Itanium ABI")
    executable = shutil.which(compiler)
    if not executable:
        raise ValueError("C++ compiler not found")
    # Keep the driver name: resolving clang++ to clang changes C++ runtime linkage.
    compiler = Path(executable).absolute()
    library = Path(library).resolve(strict=True)
    directory = Path(directory).resolve(strict=True)
    base = Path(__file__).resolve().parents[2]
    source = Path(__file__).with_name("sequence-probe.cpp")
    flags = FLAGS.copy()
    extra_sources = []
    extra_dependencies = []
    if allocations:
        hooks = source.with_name("allocation-hooks.cpp")
        extra_sources = [str(hooks)]
        extra_dependencies = [hooks, source.with_name("allocation-hooks.hpp")]
        flags += ["-DUCHARDET_ALLOCATION_PROBE", "-fno-lto"]
        flags += [
            f"-Wl,--wrap={symbol}"
            for symbol in (
                "malloc",
                "calloc",
                "realloc",
                "free",
                "_Znwm",
                "_Znam",
                "_ZdlPv",
                "_ZdaPv",
            )
        ]
    write_idempotent(directory / "sequence-model.hpp", header)
    binary = directory / "sequence-probe"
    if binary.exists():
        raise ValueError("probe output already exists; use a fresh build directory")
    dependencies = {
        str(path.relative_to(base)): digest(path.read_bytes())
        for path in (
            source,
            *extra_dependencies,
            Path(__file__),
            Path(__file__).with_name("sequence_contract.py"),
            Path(__file__).with_name("model.py"),
            base / "corpus/artifact.py",
            base / "corpus/framework.py",
            *sorted((base / "src").glob("*.h")),
        )
    }
    provenance = dict(
        **model_metadata,
        header_sha256=digest(header),
        static_library_sha256=digest(library.read_bytes()),
        compiler_sha256=digest(compiler.read_bytes()),
        compiler_driver_name=compiler.name,
        compiler_version=subprocess.run(
            [str(compiler), "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout,
        flags=flags.copy(),
        dependencies=dependencies,
    )
    subprocess.run(
        [
            str(compiler),
            *flags,
            "-I",
            str(base / "src"),
            "-I",
            str(directory),
            str(source),
            *extra_sources,
            str(library),
            "-o",
            str(binary),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    if digest(library.read_bytes()) != provenance["static_library_sha256"]:
        raise ValueError("native library changed during build")
    provenance["probe_binary_sha256"] = digest(binary.read_bytes())
    return binary, provenance


def validate_resources(resources):
    if resources is None:
        return
    fields = {
        "user_cpu_ns", "system_cpu_ns", "voluntary_switches", "involuntary_switches",
        "minor_faults", "major_faults",
    }
    if (not isinstance(resources, dict) or set(resources) != fields or
            any(type(v) is not int or not 0 <= v < 2**63 for v in resources.values())):
        raise ValueError("invalid native resource counters")


def observe(binary, data, iterations=None):
    if len(data) > 65536:
        raise ValueError("probe input exceeds 65536 bytes")
    if iterations is not None and (
        type(iterations) is not int or not 1 <= iterations <= 1000000
    ):
        raise ValueError("iterations must be an integer in [1, 1000000]")
    with tempfile.TemporaryDirectory(prefix="uchardet-sequence-input-") as temporary:
        path = Path(temporary) / "input.bin"
        path.write_bytes(data)
        command = [str(binary), str(path)]
        if iterations is not None:
            command.append(str(iterations))
        result = subprocess.run(command, check=True, capture_output=True, timeout=10)
    observation = json.loads(result.stdout)
    if observation.get("schema") != "sequence-native-probe-v1" or observation[
        "raw_bytes"
    ] != len(data):
        raise ValueError("unexpected native observation")
    if iterations is not None:
        benchmark = observation["benchmark"]
        if (
            benchmark["iterations"] != iterations
            or benchmark["warmup_iterations"] != 128
        ):
            raise ValueError("unexpected native timing policy")
        expected = int(observation["snapshot"]["confidence_bits"], 16) * iterations
        if benchmark["elapsed_ns"] <= 0 or benchmark["checksum"] != expected:
            raise ValueError("invalid native elapsed time/checksum")
        validate_resources(benchmark.get("resources"))
    return observation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("library", type=Path)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cxx", default="c++")
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    with args.input.open("rb") as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        parser.error("probe input exceeds 65536 bytes")
    with tempfile.TemporaryDirectory(prefix="uchardet-sequence-build-") as directory:
        binary, provenance = build(contract, args.library, directory, args.cxx)
        result = dict(
            provenance=provenance,
            input_sha256=digest(data),
            observation=observe(binary, data),
        )
    result["content_hash"] = content_hash(result)
    write_idempotent(args.output, canonical(result))


if __name__ == "__main__":
    main()
