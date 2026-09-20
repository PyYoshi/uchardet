# SPDX-License-Identifier: MIT
"""Fetch immutable, hashed source files; ingest offline into corpus configs."""

import argparse
import json
from pathlib import Path
import re
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from framework import digest, safe_path

MAX_DOWNLOAD = 20 * 1024 * 1024


def write_once(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"different artifact exists: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def serialized(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def validate_recipe(recipe):
    if recipe["recipe_version"] != 1 or recipe["license_choice"] != "MIT":
        raise ValueError("unsupported recipe")
    total = 0
    for repo in recipe["repositories"]:
        if not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", repo["repository"]):
            raise ValueError("invalid repository")
        if not re.fullmatch(r"[0-9a-f]{40}", repo["revision"]):
            raise ValueError("revision must be immutable commit")
        for path, sha, size in repo["files"]:
            safe_path(Path("/tmp/recipe-root"), path)
            if not re.fullmatch(r"[0-9a-f]{64}", sha) or type(size) is not int or not 0 < size <= 1024 * 1024:
                raise ValueError("invalid file hash/size")
            total += size
    if total > MAX_DOWNLOAD:
        raise ValueError("recipe exceeds download budget")
    return total


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("unexpected source redirect")


def fetch(recipe, root):
    validate_recipe(recipe)
    transferred = 0
    opener = urllib.request.build_opener(NoRedirect)
    for repo in recipe["repositories"]:
        for path, sha, size in repo["files"]:
            target = safe_path(root, f"{repo['language']}/{path}")
            if target.exists():
                data = target.read_bytes()
            else:
                url = f"https://raw.githubusercontent.com/{repo['repository']}/{repo['revision']}/{path}"
                with opener.open(url, timeout=30) as response:
                    data = response.read(size + 1)
                transferred += len(data)
            if len(data) != size or digest(data) != sha:
                raise ValueError(f"source size/hash mismatch: {path}")
            write_once(target, data)
    print(json.dumps({"transferred_bytes": transferred, "verified_bytes": validate_recipe(recipe)}))


def paragraphs(text):
    # Translation sources contain English in HTML comments; do not train on it.
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    kept, fence = [], None
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            fence = None if fence == marker else marker if fence is None else fence
            kept.append("")
        elif fence is None:
            kept.append(line)
    result = []
    for paragraph in re.split(r"\n\s*\n", "\n".join(kept)):
        paragraph = paragraph.strip()
        if not paragraph or any(line.startswith(("#", "[", "<", "    ", "{{#")) for line in paragraph.splitlines()):
            continue
        result.append(paragraph)
    return result


def ingest(recipe, root, output):
    validate_recipe(recipe)
    reports = []
    for repo in recipe["repositories"]:
        lang = repo["language"]
        files = {}
        for path, sha, size in repo["files"]:
            data = safe_path(root, f"{lang}/{path}").read_bytes()
            if len(data) != size or digest(data) != sha:
                raise ValueError("cached source hash mismatch")
            files[path] = data
        for notice in ("LICENSE-MIT", "LICENSE-APACHE", "COPYRIGHT"):
            write_once(safe_path(output, f"notices/{lang}/{notice}"), files[notice])
        for encoding in ("utf-8", repo["legacy_encoding"]):
            sources = []
            for chapter, split in recipe["chapters"]:
                path = f"{repo['prefix']}/{chapter}"
                raw = files[path]
                extracted = paragraphs(raw.decode("utf-8", errors="strict"))
                accepted = []
                for paragraph in extracted:
                    try:
                        encoded = paragraph.encode(encoding, errors="strict")
                        if encoded.decode(encoding, errors="strict") == paragraph:
                            accepted.append(paragraph)
                    except UnicodeError:
                        pass  # Whole paragraph exclusion is explicitly recorded below.
                if not accepted:
                    raise ValueError(f"no representable paragraphs: {lang}/{chapter}/{encoding}")
                text = ("\n\n".join(accepted) + "\n").encode("utf-8")
                source_id = f"rust-book-{lang}-{chapter[:-3]}-{encoding}"
                destination = f"texts/{source_id}.txt"
                write_once(safe_path(output, destination), text)
                url = f"https://github.com/{repo['repository']}/blob/{repo['revision']}/{path}"
                source = dict(id=source_id, path=destination, language=lang, license="MIT",
                    license_reference=f"https://github.com/{repo['repository']}/blob/{repo['revision']}/LICENSE-MIT", revision=repo["revision"],
                    origin=f"rust-book:{chapter}", kind="natural", sha256=digest(text), split=split,
                    source_url=url, original_sha256=digest(raw), extraction="markdown-paragraphs-v1",
                    extraction_encoding=encoding, excluded_paragraphs=len(extracted) - len(accepted),
                    retained_paragraphs=len(accepted), source_license_expression="MIT OR Apache-2.0")
                sources.append(source)
                reports.append({"id": source_id, "byte_length": len(text), "split": split,
                                "excluded_paragraphs": source["excluded_paragraphs"], "retained_paragraphs": len(accepted)})
            config = dict(sources=sources, encodings=[encoding], byte_limits=[None, 64, 1024, 4096], boundaries=["complete"], formats=["text"])
            write_once(safe_path(output, f"{lang}-{encoding}.json"), serialized(config))
    write_once(safe_path(output, "ingestion-report.json"), serialized(reports))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["fetch", "ingest"])
    parser.add_argument("recipe", type=Path)
    parser.add_argument("cache", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    recipe = json.loads(args.recipe.read_text(encoding="utf-8"))
    if args.command == "fetch":
        fetch(recipe, args.cache)
    else:
        if args.output is None:
            parser.error("ingest requires --output")
        ingest(recipe, args.cache, args.output)


if __name__ == "__main__":
    main()
