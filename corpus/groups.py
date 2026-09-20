# SPDX-License-Identifier: MIT
"""Describe connected components of overlap candidates, without rewriting corpus."""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import json
from pathlib import Path

from framework import content_hash, digest
from overlap import PROFILE, audit


def summarize(report: dict) -> dict:
    if report.get("content_hash") != content_hash(report) or report.get("profile") != PROFILE:
        raise ValueError("invalid overlap report identity")
    sources = report["sources"]
    parents = list(range(len(sources)))

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    edges = set()
    for finding in report["findings"]:
        a, b = finding["left"], finding["right"]
        if type(a) is not int or type(b) is not int or not 0 <= a < b < len(sources):
            raise ValueError("invalid candidate edge")
        if (a, b) in edges:
            raise ValueError("duplicate candidate edge")
        edges.add((a, b))
        left, right = root(a), root(b)
        parents[max(left, right)] = min(left, right)
    members = {}
    for index in range(len(sources)):
        members.setdefault(root(index), []).append(index)
    edge_counts = Counter(root(left) for left, _ in edges)
    components = []
    for identifier, indices in sorted(members.items()):
        splits = sorted({sources[i]["split"] for i in indices})
        languages = sorted({sources[i]["language"] for i in indices})
        components.append({"id": identifier, "members": indices, "size": len(indices),
                           "candidate_edges": edge_counts[identifier], "splits": splits,
                           "languages": languages, "cross_split": len(splits) > 1,
                           "illustrative_member_weight": {"numerator": 1, "denominator": len(indices)}})
    result = {"schema_version": 1, "profile": "overlap-connected-components-v1",
              "overlap_report_hash": report["content_hash"],
              "tool_sha256": digest(Path(__file__).read_bytes()),
              "status": "REVIEW_GROUPS_NOT_INDEPENDENT_SAMPLES",
              "source_count": len(sources), "component_count": len(components),
              "multi_source_components": sum(c["size"] > 1 for c in components),
              "sources_in_multi_source_components": sum(c["size"] for c in components if c["size"] > 1),
              "cross_split_components": sum(c["cross_split"] for c in components),
              "size_histogram": [{"size": size, "count": count} for size, count in
                                 sorted(Counter(c["size"] for c in components).items())],
              "sources": sources, "components": components,
              "skipped_independent": report["skipped_independent"]}
    result["content_hash"] = content_hash(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument("--threshold", type=Fraction, default=Fraction(4, 5))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = json.dumps(summarize(audit(args.manifests, args.threshold)), ensure_ascii=False,
                        sort_keys=True, indent=2) + "\n"
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
