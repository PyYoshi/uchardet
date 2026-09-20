# SPDX-License-Identifier: MIT
"""Fixed spoken-French validation pilot. No audio, native detector, or training."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from artifact import write_idempotent
from framework import digest, safe_path
from acquire import NoRedirect, serialized

REPOSITORY = "UniversalDependencies/UD_French-ParisStories"
TEXT_FILE = "fr_parisstories-ud-dev.conllu"
FILES = {"README.md", "LICENSE.txt", TEXT_FILE}
MAX_FILE_BYTES = 2 * 1024 * 1024
PROFILE = "paris-stories-recording-text-v1"


def validate_recipe(recipe):
    if (recipe.get("recipe_version") != 1 or recipe.get("repository") != REPOSITORY or
            recipe.get("license") != "CC-BY-SA-4.0" or recipe.get("upstream_split") != "dev"):
        raise ValueError("unsupported spoken corpus recipe")
    if not re.fullmatch(r"[0-9a-f]{40}", recipe["revision"]):
        raise ValueError("revision must be an immutable commit")
    if len(recipe["files"]) != 3 or {row[0] for row in recipe["files"]} != FILES:
        raise ValueError("only notices and upstream dev text are allowed")
    for _, sha, size in recipe["files"]:
        if not re.fullmatch(r"[0-9a-f]{64}", sha) or type(size) is not int or not 0 < size <= MAX_FILE_BYTES:
            raise ValueError("invalid file hash or byte budget")


def read_verified(path, sha, size):
    with path.open("rb") as stream:
        data = stream.read(size + 1)
    if len(data) != size or digest(data) != sha:
        raise ValueError("source size/hash mismatch")
    return data


def fetch(recipe, root):
    validate_recipe(recipe)
    transferred = 0
    opener = urllib.request.build_opener(NoRedirect)
    for name, sha, size in recipe["files"]:
        target = safe_path(root, name)
        if target.exists():
            read_verified(target, sha, size)
            continue
        url = f"https://raw.githubusercontent.com/{REPOSITORY}/{recipe['revision']}/{name}"
        with opener.open(url, timeout=30) as response:
            data = response.read(size + 1)
        if len(data) != size or digest(data) != sha:
            raise ValueError("download size/hash mismatch")
        write_idempotent(target, data)
        transferred += len(data)
    return {"transferred_bytes": transferred, "verified_bytes": sum(r[2] for r in recipe["files"])}


def documents(raw):
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("source byte budget exceeded")
    groups, seen_ids = {}, set()
    metadata, token_count = {}, 0

    def finish():
        nonlocal metadata, token_count
        if not metadata and not token_count:
            return
        if set(metadata) != {"sent_id", "text", "sound_url"} or not token_count:
            raise ValueError("sentence requires text, id, recording identity and token rows")
        sentence_id, text, recording = (metadata[k] for k in ("sent_id", "text", "sound_url"))
        if not sentence_id.startswith("ParisStories_") or sentence_id in seen_ids:
            raise ValueError("invalid or duplicate sentence id")
        if not text.strip() or not recording.startswith("https://api.nakala.fr/data/"):
            raise ValueError("missing text or unsupported recording identity")
        seen_ids.add(sentence_id)
        # Only hash this URL as a grouping identity. Never dereference it.
        key = digest(recording.encode("utf-8"))
        group = groups.setdefault(key, {"sentence_ids": [], "texts": []})
        group["sentence_ids"].append(sentence_id)
        group["texts"].append(text)
        metadata, token_count = {}, 0

    for line in raw.decode("utf-8", errors="strict").split("\n"):
        line = line.removesuffix("\r")
        if not line:
            finish()
        elif line.startswith("# "):
            key, separator, value = line[2:].partition(" = ")
            if separator and key in {"sent_id", "text", "sound_url"}:
                if key in metadata:
                    raise ValueError("duplicate sentence metadata")
                metadata[key] = value
        elif line.startswith("#"):
            continue
        else:
            if len(line.split("\t")) != 10:
                raise ValueError("expected ten-column CoNLL-U token row")
            token_count += 1
    finish()
    if not groups:
        raise ValueError("no documents")
    return groups


def ingest(recipe, root, output):
    validate_recipe(recipe)
    if output.exists():
        raise ValueError("output must not exist")
    cached = {name: read_verified(safe_path(root, name), sha, size)
              for name, sha, size in recipe["files"]}
    groups = documents(cached[TEXT_FILE])
    base = f"https://github.com/{REPOSITORY}/blob/{recipe['revision']}"
    sources, payloads = [], {}
    for identity, group in sorted(groups.items()):
        source_id = f"paris-fr-{identity}"
        relative = f"texts/{source_id}.txt"
        data = ("\n".join(group["texts"]) + "\n").encode("utf-8")
        payloads[relative] = data
        sources.append(dict(id=source_id, path=relative, language="fr", kind="natural",
                            license=recipe["license"], license_reference=f"{base}/LICENSE.txt",
                            revision=recipe["revision"], origin=f"parisstories:recording:{identity}",
                            sha256=digest(data), split="validation", source_url=f"{base}/{TEXT_FILE}",
                            source_file_sha256=digest(cached[TEXT_FILE]), upstream_split="dev",
                            source_kind="spoken-transcript", extraction_profile=PROFILE,
                            sentence_ids=group["sentence_ids"], recording_identity_sha256=identity))
    config = dict(sources=sources, encodings=["utf-8", "cp1252"], formats=["text"],
                  boundaries=["complete"], byte_limits=[None, 64, 1024, 4096])
    report = dict(profile=PROFILE, recipe=recipe, documents=len(sources),
                  sentences=sum(len(g["sentence_ids"]) for g in groups.values()),
                  text_bytes=sum(map(len, payloads.values())), source_split="validation",
                  legacy_representability_filter=False, audio_fetched=False,
                  native_predictions=False, tool_sha256=digest(Path(__file__).read_bytes()))
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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    recipe = json.loads(args.recipe.read_text(encoding="utf-8"))
    if args.command == "fetch":
        if args.output:
            parser.error("fetch does not use --output")
        report = fetch(recipe, args.cache)
    else:
        if not args.output:
            parser.error("ingest requires --output")
        report = ingest(recipe, args.cache, args.output)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
