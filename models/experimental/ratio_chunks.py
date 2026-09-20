# SPDX-License-Identifier: MIT
"""Bounded fixed-factor chunk observations; never tune against chunk differences."""
import argparse
import json
from pathlib import Path

import engine_comparison
import engine_probe
import paired_controls
import ratio_sweep
import ratio_variant
from model import canonical, digest, write_idempotent
from sequence_contract import content_hash

SWEEP_HASH = "8ebbe3a8e939488bf89aa1fa2c3d6169a494c99e2cf23faf9dc37419f93cd6d6"
CHUNKS = (0, 1, 7, 64, 1024)


def differences(observed, reference):
    def names(value):
        return [(c["encoding"], c["language"]) for c in value["candidates"]]
    return dict(candidate_count=observed["candidate_count"] != reference["candidate_count"],
                encoding_language_order=names(observed) != names(reference),
                exact_candidates=observed["candidates"] != reference["candidates"],
                final_done=observed["final_done"] != reference["final_done"],
                first_done_offset=observed["first_done_offset"] != reference["first_done_offset"])


def run(identity, filtered, manifest, root, sweep, directory):
    if sweep.get("content_hash") != SWEEP_HASH or content_hash(sweep) != SWEEP_HASH:
        raise ValueError("requires the frozen ratio sweep")
    if manifest["content_hash"] != identity["contract"]["provenance"]["corpus_content_hash"]:
        raise ValueError("requires the fixed training/tuning manifest")
    records, _ = paired_controls.select_pairs(identity, filtered, manifest, root, "tuning")
    if len(records) != 16 or any(len(data) > engine_probe.LIMIT for _, _, data in records):
        raise ValueError("requires all sixteen bounded tuning inputs")
    builds, saved = {}, {}
    for name, parent in (("identity", identity), ("filtered", filtered)):
        for factor in ("1", "0.90"):
            key = f"{name}-{factor}"
            previous = sweep["results"][name][factor]
            variant = previous["variant"]
            ratio_variant.validate(variant, parent)
            path = directory / f"build-{key}"
            binaries, provenance = engine_comparison.verified_build(path, variant)
            if provenance != previous["build"]:
                raise ValueError("build differs from frozen sweep")
            builds[key] = (path, variant, binaries, provenance)
            saved[key] = {row["sample_id"]: row for row in previous["documents"]}
    documents = []
    for source, sample, data in records:
        schedules = {}
        for chunk in CHUNKS:
            observations = {}
            for key, (_, _, binaries, _) in builds.items():
                normal = engine_probe.observe(binaries["uchardet-conformance"], data, chunk)
                if "legacy" in observations and normal != observations["legacy"]:
                    raise ValueError("standard targets differ")
                observations["legacy"] = normal
                value = engine_probe.observe(binaries["uchardet-conformance-experimental"], data, chunk)
                old = saved[key][sample["id"]]
                if old["sample_sha256"] != digest(data):
                    raise ValueError("tuning input differs from sweep")
                if chunk == 0 and value != old["observation"]:
                    raise ValueError("whole-input observation differs from sweep")
                observations[key] = value
            schedules[str(chunk)] = observations
        comparisons = {}
        scores = {}
        for chunk, observations in schedules.items():
            comparisons[chunk], scores[chunk] = {}, {}
            for key, value in observations.items():
                parent_key = key.replace("-0.90", "-1")
                comparisons[chunk][key] = dict(
                    vs_whole=differences(value, schedules["0"][key]),
                    vs_legacy_same_chunk=differences(value, observations["legacy"]),
                    vs_unscaled_same_chunk=differences(value, observations[parent_key]))
                scores[chunk][key] = engine_comparison.score(value, data, sample["encoding"], source["language"])
        documents.append(dict(sample_id=sample["id"], sample_sha256=sample["sha256"],
                              encoding=sample["encoding"], byte_length=len(data),
                              observations=schedules, comparisons=comparisons, scores=scores))
    for path, variant, _, provenance in builds.values():
        if engine_comparison.verified_build(path, variant)[1] != provenance:
            raise ValueError("build changed during observation")
    summary = {}
    for chunk in map(str, CHUNKS):
        summary[chunk] = {}
        for key in ("legacy", *builds):
            rows = [dict(encoding=row["encoding"], score=row["scores"][chunk][key],
                         observation=row["observations"][chunk][key]) for row in documents]
            value = ratio_sweep.summarize(rows)
            value["differences"] = {
                comparison: {field: sum(row["comparisons"][chunk][key][comparison][field] for row in documents)
                             for field in documents[0]["comparisons"][chunk][key][comparison]}
                for comparison in ("vs_whole", "vs_legacy_same_chunk", "vs_unscaled_same_chunk")}
            summary[chunk][key] = value
    result = dict(schema="paris24-fixed-ratio-chunks-v1", sweep_hash=SWEEP_HASH,
                  manifest_hash=manifest["content_hash"], chunks=list(CHUNKS),
                  documents=documents, summary=summary,
                  dependencies={p.name: digest(p.read_bytes()) for p in (Path(__file__),
                      Path(engine_probe.__file__), Path(engine_comparison.__file__),
                      Path(ratio_sweep.__file__), Path(ratio_variant.__file__), Path(paired_controls.__file__))})
    result["content_hash"] = content_hash(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("identity", "filtered", "manifest", "sweep", "builds", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    def load(path):
        return json.loads(path.read_text(encoding="utf-8"))
    result = run(load(args.identity), load(args.filtered), load(args.manifest),
                 args.manifest.parent, load(args.sweep), args.builds)
    write_idempotent(args.output, canonical(result))


if __name__ == "__main__":
    main()
