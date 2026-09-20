# SPDX-License-Identifier: MIT
"""Build/run an opt-in probe using a validated model and a trusted native static library."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from model import canonical, digest, write_idempotent
from sequence_contract import content_hash, emit_cpp, validate

FLAGS = ["-std=c++11", "-O2", "-Wall", "-Wextra", "-Wpedantic"]


def build(contract, library, directory, compiler="c++"):
    validate(contract)
    return _build(
        emit_cpp(contract),
        {"contract_hash": contract["content_hash"]},
        library,
        directory,
        compiler,
    )


def build_reference(library, directory, compiler="c++"):
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
    )


def _build(header, model_metadata, library, directory, compiler):
    executable = shutil.which(compiler)
    if not executable:
        raise ValueError("C++ compiler not found")
    # Keep the driver name: resolving clang++ to clang changes C++ runtime linkage.
    compiler = Path(executable).absolute()
    library = Path(library).resolve(strict=True)
    directory = Path(directory).resolve(strict=True)
    base = Path(__file__).resolve().parents[2]
    source = Path(__file__).with_name("sequence-probe.cpp")
    write_idempotent(directory / "sequence-model.hpp", header)
    binary = directory / "sequence-probe"
    if binary.exists():
        raise ValueError("probe output already exists; use a fresh build directory")
    dependencies = {
        str(path.relative_to(base)): digest(path.read_bytes())
        for path in (
            source,
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
            [str(compiler), "--version"], check=True, capture_output=True, text=True, timeout=10
        ).stdout,
        flags=FLAGS.copy(),
        dependencies=dependencies,
    )
    subprocess.run(
        [
            str(compiler),
            *FLAGS,
            "-I",
            str(base / "src"),
            "-I",
            str(directory),
            str(source),
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


def observe(binary, data):
    if len(data) > 65536:
        raise ValueError("probe input exceeds 65536 bytes")
    with tempfile.TemporaryDirectory(prefix="uchardet-sequence-input-") as temporary:
        path = Path(temporary) / "input.bin"
        path.write_bytes(data)
        result = subprocess.run(
            [str(binary), str(path)], check=True, capture_output=True, timeout=10
        )
    observation = json.loads(result.stdout)
    if observation.get("schema") != "sequence-native-probe-v1" or observation["raw_bytes"] != len(
        data
    ):
        raise ValueError("unexpected native observation")
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
            provenance=provenance, input_sha256=digest(data), observation=observe(binary, data)
        )
    result["content_hash"] = content_hash(result)
    write_idempotent(args.output, canonical(result))


if __name__ == "__main__":
    main()
