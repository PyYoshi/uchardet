# SPDX-License-Identifier: MIT
"""Separate upstream-train ingestion; preserve the existing validation-only pilot."""
import argparse
import json
from pathlib import Path
import re
import urllib.request

import paris_stories as pilot
from artifact import write_idempotent
from framework import audit_splits, content_hash, digest, safe_path
from acquire import NoRedirect, serialized

TEXT_FILE = "fr_parisstories-ud-train.conllu"
MAX_FILE_BYTES = 4 * 1024 * 1024
PROFILE = "paris-stories-recording-training-v1"


def validate_recipe(recipe):
    if (recipe.get("recipe_version") != 1 or recipe.get("repository") != pilot.REPOSITORY or
            recipe.get("license") != "CC-BY-SA-4.0" or recipe.get("upstream_split") != "train"):
        raise ValueError("unsupported training recipe")
    if not re.fullmatch(r"[0-9a-f]{40}", recipe["revision"]):
        raise ValueError("immutable revision required")
    if not re.fullmatch(r"[0-9a-f]{64}", recipe["validation_manifest_content_hash"]):
        raise ValueError("fixed validation manifest required")
    files = recipe["files"]
    if len(files) != 3 or {row[0] for row in files} != {"README.md", "LICENSE.txt", TEXT_FILE}:
        raise ValueError("only train text and notices are allowed")
    for _, sha, size in files:
        if not re.fullmatch(r"[0-9a-f]{64}", sha) or type(size) is not int or not 0 < size <= MAX_FILE_BYTES:
            raise ValueError("invalid source hash/size")
    quarantine = recipe.get("quarantine_sentence_ids", [])
    if (not isinstance(quarantine, list) or len(quarantine) > 100 or
            any(not isinstance(s, str) or not s.startswith("ParisStories_") for s in quarantine) or
            len(set(quarantine)) != len(quarantine)):
        raise ValueError("invalid explicit quarantine identities")
    recordings = recipe.get("quarantine_recording_ids", [])
    if (not isinstance(recordings, list) or len(recordings) > 100 or
            any(not isinstance(s, str) or not re.fullmatch(r"[0-9a-f]{64}", s) for s in recordings) or
            len(set(recordings)) != len(recordings)):
        raise ValueError("invalid explicit recording quarantine")


def partition(raw, identities):
    """Quarantine only explicitly listed records whose recording metadata is absent."""
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("source byte budget exceeded")
    expected, seen, kept, quarantine = set(identities), set(), [], []
    for block in re.split(r"\r?\n\r?\n", raw.decode("utf-8", errors="strict")):
        if not block.strip():
            continue
        lines = block.splitlines()
        ids = [line.removeprefix("# sent_id = ") for line in lines if line.startswith("# sent_id = ")]
        if len(ids) != 1 or ids[0] not in expected:
            kept.append(block)
            continue
        identity = ids[0]
        tokens = [line for line in lines if line and not line.startswith("#")]
        texts = [line for line in lines if line.startswith("# text = ")]
        if (identity in seen or any(line.startswith("# sound_url") for line in lines) or
                len(texts) != 1 or not texts[0].removeprefix("# text = ").strip() or
                not tokens or any(len(line.split("\t")) != 10 for line in tokens)):
            raise ValueError("quarantine record differs from missing-recording policy")
        seen.add(identity)
        quarantine.append(dict(sentence_id=identity, reason="MISSING_RECORDING_IDENTITY",
                               block_sha256=digest(block.encode("utf-8"))))
    if seen != expected:
        raise ValueError("explicit quarantine identity missing from input")
    return ("\n\n".join(kept) + "\n\n").encode("utf-8"), quarantine


def fetch(recipe, root):
    validate_recipe(recipe)
    opener = urllib.request.build_opener(NoRedirect)
    transferred = 0
    for name, sha, size in recipe["files"]:
        path = safe_path(root, name)
        if path.exists():
            pilot.read_verified(path, sha, size)
            continue
        url = f"https://raw.githubusercontent.com/{pilot.REPOSITORY}/{recipe['revision']}/{name}"
        with opener.open(url, timeout=30) as response:
            data = response.read(size + 1)
        if len(data) != size or digest(data) != sha:
            raise ValueError("download hash/size mismatch")
        write_idempotent(path, data)
        transferred += len(data)
    return dict(transferred_bytes=transferred, verified_bytes=sum(row[2] for row in recipe["files"]))


def ingest(recipe, root, validation, output):
    validate_recipe(recipe)
    if output.exists():
        raise ValueError("output must not exist")
    audit_splits([validation])  # Metadata only; no validation body or prediction is read.
    if validation["content_hash"] != recipe["validation_manifest_content_hash"]:
        raise ValueError("validation manifest differs from frozen recipe")
    if not validation["sources"] or any(s["split"] != "validation" for s in validation["sources"]):
        raise ValueError("validation-only reference required")
    cached = {name: pilot.read_verified(safe_path(root, name), sha, size)
              for name, sha, size in recipe["files"]}
    admitted, quarantine = partition(cached[TEXT_FILE], recipe.get("quarantine_sentence_ids", []))
    groups = pilot.documents(admitted, max_bytes=MAX_FILE_BYTES)
    validation_origins = {s["origin"] for s in validation["sources"]}
    for identity in recipe.get("quarantine_recording_ids", []):
        if identity not in groups or f"parisstories:recording:{identity}" not in validation_origins:
            raise ValueError("quarantined recording is not a validation overlap")
        group = groups.pop(identity)
        quarantine.append(dict(recording_identity_sha256=identity,
                               sentence_ids=group["sentence_ids"],
                               reason="VALIDATION_RECORDING_OVERLAP"))
    if not groups:
        raise ValueError("no admissible training recordings")
    validation_ids = {sid for s in validation["sources"] for sid in s.get("sentence_ids", [])}
    sources, payloads = [], {}
    base = f"https://github.com/{pilot.REPOSITORY}/blob/{recipe['revision']}"
    for identity, group in sorted(groups.items()):
        if validation_ids.intersection(group["sentence_ids"]):
            raise ValueError("training/validation sentence identity overlap")
        source_id = f"paris-fr-{identity}"
        relative = f"texts/{source_id}.txt"
        data = ("\n".join(group["texts"]) + "\n").encode("utf-8")
        payloads[relative] = data
        sources.append(dict(
            id=source_id, path=relative, language="fr", kind="natural",
            license=recipe["license"], license_reference=f"{base}/LICENSE.txt",
            revision=recipe["revision"], origin=f"parisstories:recording:{identity}",
            sha256=digest(data), split="training", source_url=f"{base}/{TEXT_FILE}",
            source_file_sha256=digest(cached[TEXT_FILE]), upstream_split="train",
            source_kind="spoken-transcript", extraction_profile=PROFILE,
            sentence_ids=group["sentence_ids"], recording_identity_sha256=identity,
        ))
    # Reject identical source content or recording identity across splits before any output.
    prospective = dict(schema_version=1, sources=sources)
    prospective["content_hash"] = content_hash(prospective)
    audit_splits([validation, prospective])
    config = dict(sources=sources, encodings=["utf-8", "cp1252"], formats=["text"],
                  boundaries=["complete"], byte_limits=[None])
    report = dict(profile=PROFILE, recipe=recipe, documents=len(sources),
                  sentences=sum(len(g["sentence_ids"]) for g in groups.values()),
                  text_bytes=sum(map(len, payloads.values())), source_split="training",
                  validation_manifest_content_hash=validation["content_hash"],
                  split_identity_overlap=False, semantic_independence="NOT_ESTABLISHED",
                  legacy_representability_filter=False, audio_fetched=False,
                  native_predictions=False, dependencies={
                      p.name: digest(p.read_bytes()) for p in (Path(__file__), Path(pilot.__file__))
                  }, quarantined_records=quarantine,
                  quarantine_policy="explicit missing-recording/validation-overlap identities; raw retained")
    output.mkdir(parents=True)
    for relative, data in payloads.items():
        write_idempotent(safe_path(output, relative), data)
    for name in ("README.md", "LICENSE.txt"):
        write_idempotent(output / "notices" / name, cached[name])
    write_idempotent(output / "config.json", serialized(config))
    write_idempotent(output / "ingestion-report.json", serialized(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fetch", "ingest"))
    parser.add_argument("recipe", type=Path)
    parser.add_argument("cache", type=Path)
    parser.add_argument("--validation-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    recipe = json.loads(args.recipe.read_text(encoding="utf-8"))
    if args.command == "fetch":
        if args.output or args.validation_manifest:
            parser.error("fetch does not use output/validation")
        result = fetch(recipe, args.cache)
    else:
        if not args.output or not args.validation_manifest:
            parser.error("ingest requires output and validation-manifest")
        validation = json.loads(args.validation_manifest.read_text(encoding="utf-8"))
        result = ingest(recipe, args.cache, validation, args.output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
