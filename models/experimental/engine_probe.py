# SPDX-License-Identifier: MIT
"""Opt-in French model connection to a separate, non-installed full-engine target."""
import argparse
import codecs
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import filtered_training
import sequence_training
from model import canonical, digest, write_idempotent
from sequence_contract import emit_cpp, validate

BASE = Path(__file__).resolve().parents[2]
LIMIT = 4096


def training_contract(artifact):
    if artifact.get("profile") == sequence_training.PROFILE:
        sequence_training.validate(artifact)
    elif artifact.get("profile") == filtered_training.PROFILE:
        filtered_training.validate(artifact)
    else:
        raise ValueError("unsupported frozen training profile")
    return artifact["contract"]


def build(contract, directory, compiler="c++"):
    """None is a legacy-reference adapter, not a generated replacement."""
    if sys.platform != "linux":
        raise ValueError("experimental build driver currently supports Linux only")
    if contract is not None:
        validate(contract)
        if contract["language"] != "fr" or codecs.lookup(contract["encoding"]).name != "cp1252":
            raise ValueError("only the French cp1252 slot can be replaced")
        header = emit_cpp(contract)
    else:
        header = (b'#pragma once\n#include "nsSBCharSetProber.h"\n'
                  b'#include "nsSBCharSetProber-generated.h"\n'
                  b'namespace uchardet_sequence_pilot {\n'
                  b'static const SequenceModel& model = Windows_1252FrenchModel;\n}\n')
    cmake, cxx = shutil.which("cmake"), shutil.which(compiler)
    if not cmake or not cxx:
        raise ValueError("CMake and a C++ compiler are required")
    directory = Path(directory).absolute()
    if directory.exists():
        raise ValueError("use a new experiment directory")
    paths = [BASE / "CMakeLists.txt", BASE / "benchmark/CMakeLists.txt",
             BASE / "benchmark/uchardet-conformance.cpp", Path(__file__),
             Path(__file__).with_name("sequence_contract.py"), Path(__file__).with_name("model.py")]
    paths += [p for p in (BASE / "src").rglob("*") if p.is_file() and
              (p.suffix in (".cpp", ".h", ".cmake") or p.name == "CMakeLists.txt")]
    dependencies = {str(p.relative_to(BASE)): digest(p.read_bytes()) for p in sorted(paths)}
    directory.mkdir(parents=True)
    model_path = directory / "model.hpp"
    write_idempotent(model_path, header)
    build_dir = directory / "build"
    options = ["-DCMAKE_BUILD_TYPE=Release", "-DBUILD_SHARED_LIBS=OFF", "-DBUILD_BINARY=OFF",
               "-DBUILD_TESTING=OFF", "-DBUILD_BENCHMARK=ON", f"-DCMAKE_CXX_COMPILER={cxx}",
               f"-DUCHARDET_EXPERIMENTAL_MODEL_HEADER={model_path}"]
    subprocess.run([cmake, "-S", str(BASE), "-B", str(build_dir), *options], check=True,
                   capture_output=True, timeout=60)
    names = ("uchardet-conformance", "uchardet-conformance-experimental")
    subprocess.run([cmake, "--build", str(build_dir), "--parallel", "2"],
                   check=True, capture_output=True, timeout=180)
    if (build_dir / "benchmark" / names[1]).exists():
        raise ValueError("experimental executable unexpectedly included in default build")
    subprocess.run([cmake, "--build", str(build_dir), "--target", names[1], "--parallel", "2"],
                   check=True, capture_output=True, timeout=180)
    if any(digest((BASE / path).read_bytes()) != sha for path, sha in dependencies.items()):
        raise ValueError("source changed during build")
    binaries = [build_dir / "benchmark" / name for name in names]
    provenance = dict(
        slot="Windows_1252FrenchModel", mode="reference" if contract is None else "generated",
        contract_hash=None if contract is None else contract["content_hash"],
        model_header_sha256=digest(header), dependencies=dependencies,
        cmake_version=subprocess.run([cmake, "--version"], check=True, capture_output=True,
                                     text=True, timeout=10).stdout,
        compiler_version=subprocess.run([cxx, "--version"], check=True, capture_output=True,
                                        text=True, timeout=10).stdout,
        compiler_sha256=digest(Path(cxx).read_bytes()), options=options[:-1],
        cache_configuration={line.split("=", 1)[0]: line.split("=", 1)[1]
                             for line in (build_dir / "CMakeCache.txt").read_text().splitlines()
                             if line.startswith(("CMAKE_CXX_FLAGS", "CMAKE_GENERATOR:",
                                                 "CHECK_SSE2:", "TARGET_ARCHITECTURE:"))},
        binaries={p.name: digest(p.read_bytes()) for p in binaries},
    )
    write_idempotent(directory / "provenance.json", canonical(provenance))
    return binaries, provenance


def observe(binary, data, chunk=0):
    if len(data) > LIMIT:
        raise ValueError("full-engine pilot input exceeds 4096 bytes")
    if type(chunk) is not int or chunk not in (0, 1, 7, 64, 1024):
        raise ValueError("unsupported pilot chunk schedule")
    with tempfile.TemporaryDirectory(prefix="uchardet-engine-input-") as temporary:
        path = Path(temporary) / "input.bin"
        path.write_bytes(data)
        result = subprocess.run([str(binary), "fresh", str(chunk), str(path)], check=True,
                                capture_output=True, timeout=10)
    record = json.loads(result.stdout)
    if (record.get("schema_version") != 1 or record["input_index"] != 0 or
            record["byte_length"] != len(data) or
            type(record["candidate_count"]) is not int or
            record["candidate_count"] != len(record["candidates"])):
        raise ValueError("unexpected candidate observation")
    for candidate in record["candidates"]:
        if not re.fullmatch(r"[0-9a-f]{8}", candidate["confidence_bits"]):
            raise ValueError("invalid confidence bit pattern")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--training", type=Path)
    source.add_argument("--reference", action="store_true")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--cxx", default="c++")
    args = parser.parse_args()
    contract = None if args.reference else training_contract(
        json.loads(args.training.read_text(encoding="utf-8")))
    build(contract, args.directory, args.cxx)


if __name__ == "__main__":
    main()
