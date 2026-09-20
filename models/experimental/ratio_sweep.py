# SPDX-License-Identifier: MIT
"""Run only the predeclared Paris24 tuning sensitivity experiment."""
import argparse
import json
import math
from pathlib import Path
import struct

import engine_comparison
import engine_probe
import paired_controls
import ratio_variant
from model import canonical, digest, write_idempotent
from sequence_contract import content_hash

BASELINE_HASH = "d34ffb575ce241519978ff704c9da96c821f67f3cae39dff54cbbde23f6ea9a6"


def summarize(rows):
    result = {}
    for encoding in ("cp1252", "utf-8"):
        selected = [row for row in rows if row["encoding"] == encoding]
        result[encoding] = dict(samples=len(selected),
            exact=sum(row["score"]["top1_exact_codec"] for row in selected),
            decoded=sum(row["score"]["top1_decode_status"] == "equal" for row in selected),
            language=sum(row["score"]["top1_language_match"] for row in selected),
            candidate_present=sum(bool(row["score"]["expected_candidate_ranks"]) for row in selected))
    values = [struct.unpack("!f", bytes.fromhex(c["confidence_bits"]))[0]
              for row in rows for c in row["observation"]["candidates"]]
    result["invalid_confidences"] = sum(not math.isfinite(v) or not 0 <= v <= 1 for v in values)
    return result


def eligible(candidate, baseline):
    return (candidate["invalid_confidences"] == 0 and
            candidate["cp1252"]["decoded"] > baseline["cp1252"]["decoded"] and
            all(candidate["utf-8"][key] >= baseline["utf-8"][key] for key in ("exact", "decoded")) and
            all(candidate[encoding]["language"] >= baseline[encoding]["language"]
                for encoding in ("cp1252", "utf-8")))


def run(identity, filtered, manifest, root, baseline, directory):
    if baseline.get("content_hash") != BASELINE_HASH or content_hash(baseline) != BASELINE_HASH:
        raise ValueError("requires the frozen Paris24 baseline")
    parents = {"identity": identity, "filtered": filtered}
    if (manifest["content_hash"] != baseline["corpus_content_hash"] or
            {name: parent["content_hash"] for name, parent in parents.items()} != baseline["training_hashes"]):
        raise ValueError("experiment inputs differ from preregistered baseline")
    records, _ = paired_controls.select_pairs(identity, filtered, manifest, root, "tuning")
    if len(records) != 16 or any(len(data) > engine_probe.LIMIT for _, _, data in records):
        raise ValueError("requires all sixteen bounded tuning inputs")
    saved = {row["sample_id"]: row for row in baseline["documents"]}
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, parent in parents.items():
        results[name] = {}
        for factor in ratio_variant.FACTORS:
            variant = ratio_variant.derive(parent, factor)
            variant_path = directory / f"{name}-{factor}.json"
            write_idempotent(variant_path, canonical(variant))
            build_dir = directory / f"build-{name}-{factor}"
            if not build_dir.exists():
                engine_probe.build(variant["contract"], build_dir)
            # Reuse is allowed only after exact contract/source/binary verification.
            binaries, provenance = engine_comparison.verified_build(build_dir, variant)
            rows = []
            for source, sample, data in records:
                previous = saved[sample["id"]]
                if previous["sample_sha256"] != digest(data):
                    raise ValueError("baseline input hash mismatch")
                normal = engine_probe.observe(binaries["uchardet-conformance"], data)
                if normal != previous["observations"]["legacy"]:
                    raise ValueError("standard engine differs from frozen baseline")
                observed = engine_probe.observe(binaries["uchardet-conformance-experimental"], data)
                if factor == "1" and observed != previous["observations"][name]:
                    raise ValueError("factor one differs from frozen baseline")
                rows.append(dict(sample_id=sample["id"], sample_sha256=sample["sha256"],
                    encoding=sample["encoding"], observation=observed,
                    score=engine_comparison.score(observed, data, sample["encoding"], source["language"])))
            _, after = engine_comparison.verified_build(build_dir, variant)
            if after != provenance:
                raise ValueError("build changed during observation")
            results[name][factor] = dict(variant=variant, build=provenance,
                                        documents=rows, summary=summarize(rows))
    decisions = {}
    for name, variants in results.items():
        candidates = [factor for factor, value in variants.items()
                      if eligible(value["summary"], variants["1"]["summary"])]
        candidates.sort(key=lambda factor: (
            variants[factor]["summary"]["cp1252"]["decoded"],
            variants[factor]["summary"]["cp1252"]["exact"], float(factor)), reverse=True)
        decisions[name] = dict(eligible_factors=candidates,
                               next_stage_candidate=candidates[0] if candidates else None,
                               deployment_approved=False)
    report = dict(schema="paris24-ratio-sensitivity-v1", baseline_hash=BASELINE_HASH,
                  results=results, decisions=decisions,
                  dependencies={path.name: digest(path.read_bytes()) for path in (
                      Path(__file__), Path(ratio_variant.__file__),
                      Path(engine_comparison.__file__), Path(paired_controls.__file__),
                      Path(__file__).with_name("RATIO_VARIANT.ja.md"))})
    report["content_hash"] = content_hash(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("identity", "filtered", "manifest", "baseline", "builds", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    def load(path):
        return json.loads(path.read_text(encoding="utf-8"))
    report = run(load(args.identity), load(args.filtered), load(args.manifest),
                 args.manifest.parent, load(args.baseline), args.builds)
    write_idempotent(args.output, canonical(report))


if __name__ == "__main__":
    main()
