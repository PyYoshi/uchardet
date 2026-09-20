# SPDX-License-Identifier: MIT
"""Bounded, source-only overlap diagnostics; never runs a detector."""

from __future__ import annotations

import argparse
from fractions import Fraction
import itertools
import json
from pathlib import Path
import unicodedata

from framework import audit_splits, content_hash, digest, safe_path

PROFILE = "nfkc-casefold-whitespace-char5-v1"
MAX_BYTES = 8 * 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024
MAX_SOURCES = 1000


def bounded_read(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input byte budget exceeded")
    return data


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def audit(paths: list[Path], threshold: Fraction = Fraction(4, 5)) -> dict:
    if not 0 < threshold <= 1:
        raise ValueError("threshold must be in (0, 1]")
    if not paths or len(paths) > MAX_SOURCES:
        raise ValueError("invalid manifest count")
    manifests = []
    manifest_bytes = 0
    for path in paths:
        raw = bounded_read(path, MAX_BYTES - manifest_bytes)
        manifest_bytes += len(raw)
        manifests.append((json.loads(raw), path.parent))
    # Known hash/origin leakage is an invalid input, not a heuristic finding.
    audit_splits([manifest for manifest, _ in manifests])
    if sum(len(m["sources"]) for m, _ in manifests) > MAX_SOURCES:
        raise ValueError("source count budget exceeded")
    identities = [m["content_hash"] for m, _ in manifests]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate manifest")
    records, texts, grams = [], [], []
    skipped = []
    total_bytes = 0
    for manifest, root in sorted(manifests, key=lambda pair: pair[0]["content_hash"]):
        for source in sorted(manifest["sources"], key=lambda item: item["id"]):
            identity = {key: source[key] for key in
                        ("id", "sha256", "origin", "language", "split")}
            identity["manifest_hash"] = manifest["content_hash"]
            if source["split"] == "independent":
                skipped.append(identity)
                continue
            raw = bounded_read(safe_path(root, source["path"]),
                               min(MAX_SOURCE_BYTES, MAX_BYTES - total_bytes))
            total_bytes += len(raw)
            text = raw.decode("utf-8", errors="strict")
            if (digest(raw) != source["sha256"] or
                    len(raw) != source.get("byte_length") or
                    len(text) != source.get("character_length")):
                raise ValueError("source hash or length mismatch")
            normalized = normalize(text)
            if len(normalized.encode("utf-8")) > MAX_SOURCE_BYTES:
                raise ValueError("normalized source budget exceeded")
            records.append(identity | {"normalized_hash": digest(normalized.encode("utf-8")),
                                       "normalized_characters": len(normalized)})
            texts.append(normalized)
            grams.append({normalized[i:i + 5] for i in range(len(normalized) - 4)})
    findings = []
    comparisons = 0
    if sum(map(len, grams)) * max(0, len(grams) - 1) > 50_000_000:
        raise ValueError("pair comparison work budget exceeded")
    for left, right in itertools.combinations(range(len(records)), 2):
        comparisons += 1
        equal = bool(texts[left]) and texts[left] == texts[right]
        # Empty/short sources have no near-match evidence. Equality is separate.
        intersection = len(grams[left] & grams[right])
        union = len(grams[left]) + len(grams[right]) - intersection
        near = (bool(grams[left]) and bool(grams[right]) and
                intersection * threshold.denominator >= union * threshold.numerator)
        if equal or near:
            findings.append({"left": left, "right": right,
                             "kind": "normalized_equal" if equal else "near_duplicate_candidate",
                             "cross_split": records[left]["split"] != records[right]["split"],
                             "same_origin": records[left]["origin"] == records[right]["origin"],
                             "intersection": intersection, "union": union})
    report = {"schema_version": 1, "profile": PROFILE,
              "unicode_version": unicodedata.unidata_version,
              "tool_sha256": digest(Path(__file__).read_bytes()),
              "framework_sha256": digest(Path(__file__).with_name("framework.py").read_bytes()),
              "threshold": {"numerator": threshold.numerator, "denominator": threshold.denominator},
              "scope": "source-only; independent bodies and generated samples not read",
              "sources": records, "skipped_independent": skipped,
              "source_bytes": total_bytes, "pair_comparisons": comparisons,
              "findings": findings, "status": "DIAGNOSTIC_NOT_LEAKAGE_CLEARANCE"}
    report["content_hash"] = content_hash(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument("--threshold", type=Fraction, default=Fraction(4, 5))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = json.dumps(audit(args.manifests, args.threshold), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            if args.output.read_text(encoding="utf-8") != output:
                raise ValueError("refusing to overwrite different report")
        else:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
