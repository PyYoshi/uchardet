# SPDX-License-Identifier: MIT
"""Frozen sensitivity variants, not calibrated probability estimates or deployment models."""
import argparse
import copy
import json
from pathlib import Path
import struct

from engine_probe import training_contract
from model import canonical, digest, write_idempotent
from sequence_contract import content_hash, ratio, validate as validate_contract

FACTORS = {"1": (1, 1), "0.95": (19, 20), "0.90": (9, 10), "0.80": (4, 5)}
PROFILE = "french-ratio-sensitivity-v1"


def derive(parent, factor):
    if not isinstance(factor, str) or factor not in FACTORS:
        raise ValueError("factor must belong to the frozen sensitivity grid")
    contract = copy.deepcopy(training_contract(parent))
    if contract["language"] != "fr":
        raise ValueError("French-only sensitivity experiment")
    numerator, denominator = FACTORS[factor]
    tool_hash = digest(Path(__file__).read_bytes())
    if factor != "1":
        value = ratio(contract) * numerator / denominator
        contract["typical_positive_ratio_bits"] = struct.pack("!f", value).hex()
        contract["generation_parameters"]["typical_positive_ratio"] = (
            f"parent binary32 ratio multiplied by {numerator}/{denominator}; rounded to binary32; sensitivity only")
        contract["provenance"]["generator_version"] = PROFILE
        contract["provenance"]["generator_source_sha256"] = digest(canonical({
            "parent_artifact": parent["content_hash"], "variant_tool": tool_hash}))
        contract["content_hash"] = content_hash(contract)
    validate_contract(contract)
    result = dict(profile=PROFILE, deployment_status="SENSITIVITY_ONLY_NOT_CALIBRATED",
                  parent_artifact_hash=parent["content_hash"], factor=factor,
                  factor_fraction=[numerator, denominator], tool_sha256=tool_hash,
                  contract=contract)
    result["content_hash"] = content_hash(result)
    return result


def validate(artifact, parent):
    if canonical(artifact) != canonical(derive(parent, artifact.get("factor"))):
        raise ValueError("variant differs from the verified parent and frozen transform")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parent", type=Path)
    parser.add_argument("factor", choices=FACTORS)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    parent = json.loads(args.parent.read_text(encoding="utf-8"))
    write_idempotent(args.output, canonical(derive(parent, args.factor)))


if __name__ == "__main__":
    main()
