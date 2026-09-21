# SPDX-License-Identifier: MIT
"""Frozen small tuning/validation pilot; not independent evaluation or selection."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "models/experimental"))
import engine_comparison
from engine_comparison import score
from framework import content_hash as manifest_hash
from model import canonical, write_idempotent
from sequence_contract import content_hash

FROZEN = "5d28f112f1ed472e1a438df9790f9e2f50c9aa0e216943059e2bb51621d0c8c1"
VALIDATION = "7b4695e8ff78effdeca177f71cf761081b46c64427ae8ad5c1d58de02e7e7265"
BLOCKS = (1, 7, 64, 1024)
CHUNKS = (0, 1, 7, 64, 1024)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(manifest_path, previous_path, binary, baseline, split="tuning"):
    if split not in ("tuning", "validation"):
        raise ValueError("independent/unknown split is not permitted")
    manifest = json.loads(manifest_path.read_text())
    previous = json.loads(previous_path.read_text())
    frozen = FROZEN if split == "tuning" else VALIDATION
    expected_count = 16 if split == "tuning" else 32
    if previous.get("content_hash") != frozen or content_hash(previous) != frozen:
        raise ValueError("requires frozen report for selected split")
    corpus_hash = previous["manifest_hash" if split == "tuning" else "corpus_content_hash"]
    if manifest_hash(manifest) != corpus_hash:
        raise ValueError("manifest differs from frozen run")
    records = previous["documents"]
    if split == "validation":
        if previous["split"] != "validation":
            raise ValueError("prior report is not validation")
        records = [
            dict(
                row,
                encoding=row["sample_encoding"],
                observations={"0": {"legacy": row["observations"]["legacy"]}},
            )
            for row in records
        ]
    samples = {s["id"]: s for s in manifest["samples"]}
    if len(samples) != len(manifest["samples"]):
        raise ValueError("duplicate sample IDs")
    hashes = {"adapter": sha(binary), "baseline": sha(baseline)}
    documents = []
    for old in records:
        sample = samples[old["sample_id"]]
        if (
            sample["split"] != split
            or sample["boundary"] != "complete"
            or sample["encoding"] != old["encoding"]
            or sample["sha256"] != old["sample_sha256"]
        ):
            raise ValueError("only complete samples from selected split are allowed")
        root = manifest_path.parent.resolve()
        path = (root / sample["path"]).resolve()
        if not path.is_relative_to(root) or path.stat().st_size > 4096:
            raise ValueError("input outside bounded pilot")
        data = path.read_bytes()
        if sha(path) != old["sample_sha256"] or len(data) != old["byte_length"]:
            raise ValueError("input changed")

        def observe(executable, args):
            return json.loads(
                subprocess.run(
                    [str(executable), *map(str, args), str(path)],
                    capture_output=True,
                    check=True,
                    text=True,
                    timeout=10,
                ).stdout
            )

        normal = observe(baseline, ["fresh", 0])
        if normal != old["observations"]["0"]["legacy"]:
            raise ValueError("baseline differs from frozen observation")
        blocks = {}
        for block in BLOCKS:
            observations = {
                str(chunk): observe(binary, [block, 4096, "fresh", chunk]) for chunk in CHUNKS
            }
            stable = (
                "candidates",
                "candidate_count",
                "initial_done",
                "final_done",
                "core_processed_bytes",
                "core_feed_calls",
                "core_first_done_offset",
            )
            reference = observations["0"]
            for observation in observations.values():
                if any(observation[key] != reference[key] for key in stable):
                    raise ValueError("external chunk changed canonical result")
            blocks[str(block)] = dict(
                observations=observations,
                score=score(reference, data, sample["encoding"], "fr"),
                vs_legacy_whole_candidates=reference["candidates"] != normal["candidates"],
                vs_legacy_whole_done=reference["final_done"] != normal["final_done"],
            )
        documents.append(
            dict(
                sample_id=sample["id"],
                sha256=sha(path),
                encoding=sample["encoding"],
                byte_length=len(data),
                blocks=blocks,
                baseline_score=score(normal, data, sample["encoding"], "fr"),
            )
        )
    if len(documents) != expected_count:
        raise ValueError("unexpected number of frozen inputs")
    if hashes != {"adapter": sha(binary), "baseline": sha(baseline)}:
        raise ValueError("binary changed during evaluation")
    summary = {}
    for block in map(str, BLOCKS):
        summary[block] = {}
        for encoding in ("cp1252", "utf-8"):
            rows = [d for d in documents if d["encoding"] == encoding]
            summary[block][encoding] = dict(
                samples=len(rows),
                exact=sum(d["blocks"][block]["score"]["top1_exact_codec"] for d in rows),
                decode_equal=sum(
                    d["blocks"][block]["score"]["top1_decode_status"] == "equal" for d in rows
                ),
                changed_candidates=sum(
                    d["blocks"][block]["vs_legacy_whole_candidates"] for d in rows
                ),
            )
    result = dict(
        schema="fixed-block-" + split + "-pilot-v1",
        split=split,
        previous_hash=frozen,
        manifest_hash=corpus_hash,
        binary_hashes=hashes,
        driver_hash=sha(Path(__file__)),
        blocks=list(BLOCKS),
        chunks=list(CHUNKS),
        score_driver_hash=sha(Path(engine_comparison.__file__)),
        evidence_limit=4096,
        documents=documents,
        summary=summary,
        compatible_superset_metric="NOT_EVALUATED",
        independent_holdout="NOT_OPENED",
    )
    result["content_hash"] = content_hash(result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "previous", "binary", "baseline", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--split", choices=("tuning", "validation"), default="tuning")
    args = parser.parse_args()
    result = run(
        args.manifest, args.previous, args.binary.resolve(), args.baseline.resolve(), args.split
    )
    write_idempotent(args.output, canonical(result))
    print(json.dumps(result["summary"], indent=2))
