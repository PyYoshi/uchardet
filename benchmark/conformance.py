# SPDX-License-Identifier: MIT
# Copyright (c) 2026 cChardet contributors
"""Offline C API regression/chunk/lifecycle comparison (Python >= 3.11)."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import tempfile

SCHEDULES = ("0", "1", "7", "64", "1024", "random")


def fixtures():
    rng = random.Random(20260920)
    return {
        "empty": b"", "nul": b"\0", "ascii": b"plain text\n" * 100,
        "embedded-nul": b"hello\0world\0" * 20,
        "utf8": ("日本語の文章です。" * 100).encode(),
        "utf8-bom": b"\xef\xbb\xbfhello", "utf16-bom": b"\xff\xfe" + "日本語".encode("utf-16le"),
        "malformed": b"\xff\xfe\xc0\xaf\xed\xa0\x80\xf4\x90\x80\x80" * 100,
        **{f"random-{size}": rng.randbytes(size) for size in (1, 2, 7, 64, 1024, 4096)},
    }


def run(tool, mode, schedule, paths):
    result = subprocess.run([str(tool), mode, schedule, *map(str, paths)],
                            check=True, capture_output=True, text=True, timeout=120)
    records = [json.loads(line) for line in result.stdout.splitlines()]
    if len(records) != len(paths):
        raise ValueError("unexpected output record count")
    for index, record in enumerate(records):
        if record["schema_version"] != 1 or record["input_index"] != index:
            raise ValueError("unexpected output schema or input order")
        if record["candidate_count"] != len(record["candidates"]):
            raise ValueError("candidate count mismatch")
    return records


def semantic(record):
    # Completion offsets depend on observation boundaries, not just detector state.
    return {key: record[key] for key in ("candidates", "initial_done", "final_done")}


def differences(left, right, label, exact=True):
    return [{"input_index": i, "comparison": label, "before": a, "after": b}
            for i, (a, b) in enumerate(zip(left, right, strict=True))
            if (a if exact else semantic(a)) != (b if exact else semantic(b))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--strict-chunks", action="store_true")
    parser.add_argument("inputs", type=Path, nargs="*")
    args = parser.parse_args()
    report = {"schema_version": 1, "regressions": [], "reset_differences": [],
              "chunk_differences": [], "observations": {}}
    with tempfile.TemporaryDirectory(prefix="uchardet-conformance-") as directory:
        paths = []
        for name, data in fixtures().items():
            path = Path(directory) / name
            path.write_bytes(data)
            paths.append(path)
        paths += args.inputs
        # Revisit the complete sequence to exercise reset after different input types.
        paths *= 2
        report["inputs"] = [{"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                            for p in paths]
        report["executables"] = {"current": {"path": str(args.tool.resolve()),
                                  "sha256": hashlib.sha256(args.tool.read_bytes()).hexdigest()}}
        if args.baseline:
            report["executables"]["baseline"] = {"path": str(args.baseline.resolve()),
                "sha256": hashlib.sha256(args.baseline.read_bytes()).hexdigest()}
        for schedule in SCHEDULES:
            fresh = run(args.tool.resolve(), "fresh", schedule, paths)
            reuse = run(args.tool.resolve(), "reuse", schedule, paths)
            report["observations"][schedule] = {"fresh": fresh, "reuse": reuse}
            report["reset_differences"] += differences(fresh, reuse, f"fresh/reuse:{schedule}")
            if schedule == "0":
                whole = fresh
            else:
                report["chunk_differences"] += differences(whole, fresh, f"0/{schedule}", exact=False)
            if args.baseline:
                for mode, current in (("fresh", fresh), ("reuse", reuse)):
                    baseline = run(args.baseline.resolve(), mode, schedule, paths)
                    report["regressions"] += differences(baseline, current, f"baseline/current:{mode}:{schedule}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(report["regressions"] or report["reset_differences"] or
                    (args.strict_chunks and report["chunk_differences"])))


if __name__ == "__main__":
    raise SystemExit(main())
