# SPDX-License-Identifier: MIT
"""Frozen small tuning pilot; not independent evaluation or block selection."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "models/experimental"))
from engine_comparison import score
from model import canonical, write_idempotent
from sequence_contract import content_hash
from framework import content_hash as manifest_hash

FROZEN = "5d28f112f1ed472e1a438df9790f9e2f50c9aa0e216943059e2bb51621d0c8c1"
BLOCKS = (1, 7, 64, 1024)
CHUNKS = (0, 1, 7, 64, 1024)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(manifest_path, previous_path, binary, baseline):
    manifest = json.loads(manifest_path.read_text())
    previous = json.loads(previous_path.read_text())
    if previous.get("content_hash") != FROZEN or content_hash(previous) != FROZEN:
        raise ValueError("requires frozen tuning chunk report")
    if manifest_hash(manifest) != previous["manifest_hash"]:
        raise ValueError("manifest differs from frozen tuning run")
    samples = {s["id"]: s for s in manifest["samples"]}
    hashes = {"adapter": sha(binary), "baseline": sha(baseline)}
    documents = []
    for old in previous["documents"]:
        sample = samples[old["sample_id"]]
        if sample["split"] != "tuning" or sample["boundary"] != "complete":
            raise ValueError("only complete tuning samples are allowed")
        root = manifest_path.parent.resolve()
        path = (root / sample["path"]).resolve()
        if not path.is_relative_to(root) or path.stat().st_size > 4096:
            raise ValueError("input outside bounded pilot")
        data = path.read_bytes()
        if sha(path) != old["sample_sha256"] or len(data) != old["byte_length"]:
            raise ValueError("input changed")

        def observe(executable, args):
            return json.loads(subprocess.run(
                [str(executable), *map(str, args), str(path)],
                capture_output=True, check=True, text=True, timeout=10).stdout)

        normal = observe(baseline, ["fresh", 0])
        if normal != old["observations"]["0"]["legacy"]:
            raise ValueError("baseline differs from frozen observation")
        blocks = {}
        for block in BLOCKS:
            observations = {str(chunk): observe(binary, [block, 4096, "fresh", chunk])
                            for chunk in CHUNKS}
            stable = ("candidates", "candidate_count", "initial_done", "final_done",
                      "core_processed_bytes", "core_feed_calls", "core_first_done_offset")
            reference = observations["0"]
            for observation in observations.values():
                if any(observation[key] != reference[key] for key in stable):
                    raise ValueError("external chunk changed canonical result")
            blocks[str(block)] = dict(observations=observations,
                score=score(reference, data, sample["encoding"], "fr"),
                vs_legacy_whole_candidates=reference["candidates"] != normal["candidates"],
                vs_legacy_whole_done=reference["final_done"] != normal["final_done"])
        documents.append(dict(sample_id=sample["id"], sha256=sha(path),
            encoding=sample["encoding"], byte_length=len(data), blocks=blocks,
            baseline_score=score(normal, data, sample["encoding"], "fr")))
    if len(documents) != 16:
        raise ValueError("expected sixteen frozen tuning inputs")
    if hashes != {"adapter": sha(binary), "baseline": sha(baseline)}:
        raise ValueError("binary changed during evaluation")
    summary = {}
    for block in map(str, BLOCKS):
        summary[block] = {}
        for encoding in ("cp1252", "utf-8"):
            rows = [d for d in documents if d["encoding"] == encoding]
            summary[block][encoding] = dict(samples=len(rows),
                exact=sum(d["blocks"][block]["score"]["top1_exact_codec"] for d in rows),
                decode_equal=sum(d["blocks"][block]["score"]["top1_decode_status"] == "equal" for d in rows),
                changed_candidates=sum(d["blocks"][block]["vs_legacy_whole_candidates"] for d in rows))
    result = dict(schema="fixed-block-tuning-pilot-v1", previous_hash=FROZEN,
        manifest_hash=previous["manifest_hash"], binary_hashes=hashes,
        driver_hash=sha(Path(__file__)), blocks=list(BLOCKS), chunks=list(CHUNKS),
        evidence_limit=4096, documents=documents, summary=summary,
        compatible_superset_metric="NOT_EVALUATED", independent_holdout="NOT_OPENED")
    result["content_hash"] = content_hash(result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "previous", "binary", "baseline", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    result = run(args.manifest, args.previous, args.binary.resolve(), args.baseline.resolve())
    write_idempotent(args.output, canonical(result))
    print(json.dumps(result["summary"], indent=2))
