# SPDX-License-Identifier: MIT
"""Offline, deterministic corpus generation. No third-party dependencies."""

from __future__ import annotations

import argparse
import codecs
import hashlib
import html
import json
import platform
import re
from pathlib import Path

SPLITS = {"training", "tuning", "validation", "independent"}
ID = re.compile(r"[A-Za-z0-9_-]+\Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_hash(manifest: dict) -> str:
    """Operational timestamps are not part of reproducible content identity."""
    content = {k: v for k, v in manifest.items() if k not in {"generated_at", "content_hash"}}
    return digest(json.dumps(content, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8"))


def safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("invalid relative path")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("path traversal")
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("path escapes corpus root")
    return target


def required(record: dict, names: tuple[str, ...]) -> None:
    for name in names:
        if not isinstance(record.get(name), str) or not record[name].strip():
            raise ValueError(f"missing {name}")


def check_source(source: dict) -> None:
    required(source, ("id", "path", "language", "license", "license_reference",
                      "revision", "origin", "sha256", "split", "kind"))
    if not ID.fullmatch(source["id"]) or source["split"] not in SPLITS:
        raise ValueError("invalid source id or split")
    if source["kind"] not in {"synthetic", "natural"}:
        raise ValueError("invalid source kind")


def encode_variant(text: str, encoding: str, limit: int | None,
                   boundary: str) -> tuple[bytes, int | None]:
    full = text.encode(encoding, errors="strict")
    if full.decode(encoding, errors="strict") != text:
        raise ValueError("source cannot round-trip in requested encoding")
    if limit is not None and (type(limit) is not int or limit <= 0):
        raise ValueError("byte limit must be positive integer or null")
    if boundary not in {"complete", "truncated"}:
        raise ValueError("invalid boundary mode")
    if boundary == "truncated":
        return full if limit is None else full[:limit], None
    if limit is None or len(full) <= limit:
        return full, len(text)
    # Account for finalized prefixes, including stateful reset sequences/BOM.
    # Clone encoder state to measure finalization without repeatedly encoding text.
    encoder_type = codecs.getincrementalencoder(encoding)
    encoder = encoder_type(errors="strict")
    emitted, length = 0, 0
    found = False
    for end in range(len(text) + 1):
        if end:
            emitted += len(encoder.encode(text[end - 1], final=False))
        finalizer = encoder_type(errors="strict")
        finalizer.setstate(encoder.getstate())
        final_size = emitted + len(finalizer.encode("", final=True))
        if final_size <= limit:
            length, found = end, True
    result = text[:length].encode(encoding, errors="strict") if found else b""
    if len(result) > limit or (result and result.decode(encoding, errors="strict") != text[:length]):
        raise ValueError("incremental codec cannot reproduce finalized prefix")
    return result, length


def validate(manifest: dict, root: Path) -> None:
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported schema version")
    if manifest.get("content_hash") != content_hash(manifest):
        raise ValueError("manifest content hash mismatch")
    sources, source_hashes, origins = {}, {}, {}
    for source in manifest["sources"]:
        check_source(source)
        if source["id"] in sources:
            raise ValueError("duplicate source id")
        data = safe_path(root, source["path"]).read_bytes()
        text = data.decode("utf-8", errors="strict")
        if digest(data) != source["sha256"]:
            raise ValueError("source hash mismatch")
        if source.get("byte_length") != len(data) or source.get("character_length") != len(text):
            raise ValueError("source size mismatch")
        # Renaming an identical document or revising the same origin must not leak splits.
        for groups, key in ((source_hashes, source["sha256"]), (origins, source["origin"])):
            if key in groups and groups[key] != source["split"]:
                raise ValueError("source split leakage")
            groups[key] = source["split"]
        sources[source["id"]] = (source, text)
    seen = set()
    for sample in manifest["samples"]:
        required(sample, ("id", "path", "source_id", "encoding", "encoder", "encoder_version", "sha256"))
        if sample["id"] in seen:
            raise ValueError("duplicate sample id")
        seen.add(sample["id"])
        if sample["source_id"] not in sources:
            raise ValueError("unknown sample source")
        source, text = sources[sample["source_id"]]
        if sample.get("split") != source["split"]:
            raise ValueError("variant split leakage")
        payload, declaration = render(text, sample["format"], sample["encoding"])
        if sample.get("declared_encoding") != declaration:
            raise ValueError("declaration metadata mismatch")
        expected, chars = encode_variant(payload, sample["encoding"], sample["byte_limit"], sample["boundary"])
        data = safe_path(root, sample["path"]).read_bytes()
        if data != expected or digest(data) != sample["sha256"]:
            raise ValueError("sample content mismatch")
        if sample.get("byte_length") != len(data) or sample.get("character_length") != chars:
            raise ValueError("sample size mismatch")


def render(text: str, format: str, encoding: str) -> tuple[str, str | None]:
    if format == "text":
        return text, None
    if format not in {"html-clean", "html-declared", "html-mismatched"}:
        raise ValueError("unknown format")
    declaration = None
    if format == "html-declared":
        declaration = encoding
    elif format == "html-mismatched":
        declaration = "windows-1252" if codecs.lookup(encoding).name == "utf-8" else "utf-8"
    meta = "" if declaration is None else f'<meta charset="{declaration}">'
    return f"<!doctype html><html><head>{meta}</head><body>{html.escape(text)}</body></html>", declaration


def generate(config: dict, source_root: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("output must not exist (never overwrite corpus artifacts)")
    sources, samples, files = [], [], {}
    for original in config["sources"]:
        check_source(original)
        data = safe_path(source_root, original["path"]).read_bytes()
        if digest(data) != original["sha256"]:
            raise ValueError("source hash mismatch")
        text = data.decode("utf-8", errors="strict")
        source = dict(original, path=f"sources/{original['id']}.txt", byte_length=len(data), character_length=len(text))
        sources.append(source)
        files[source["path"]] = data
        for encoding in config["encodings"]:
            encoding = codecs.lookup(encoding).name
            for format in config.get("formats", ["text"]):
                payload, declaration = render(text, format, encoding)
                for boundary in config.get("boundaries", ["complete"]):
                    for limit in config.get("byte_limits", [None]):
                        encoded, chars = encode_variant(payload, encoding, limit, boundary)
                        sample_id = f"{source['id']}-{encoding}-{format}-{boundary}-{limit}"
                        sample = dict(id=sample_id, path=f"samples/{sample_id}.bin", source_id=source["id"],
                                      split=source["split"], encoding=encoding, format=format,
                                      declared_encoding=declaration, byte_limit=limit, boundary=boundary,
                                      byte_length=len(encoded), character_length=chars, sha256=digest(encoded),
                                      encoder="python-codecs", encoder_version=f"{platform.python_implementation()} {platform.python_version()}")
                        samples.append(sample)
                        if sample["path"] in files:
                            raise ValueError("duplicate variant")
                        files[sample["path"]] = encoded
    manifest = dict(schema_version=1, sources=sources, samples=samples)
    manifest["content_hash"] = content_hash(manifest)
    # All encoding operations finish before writing; the output is never updated in place.
    output.mkdir(parents=True)
    for path, data in files.items():
        target = safe_path(output, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    validate(manifest, output)
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    gen = commands.add_parser("generate")
    gen.add_argument("config", type=Path)
    gen.add_argument("output", type=Path)
    check = commands.add_parser("validate")
    check.add_argument("manifest", type=Path)
    args = parser.parse_args()
    if args.command == "generate":
        generate(json.loads(args.config.read_text(encoding="utf-8")), args.config.parent, args.output)
    else:
        validate(json.loads(args.manifest.read_text(encoding="utf-8")), args.manifest.parent)


if __name__ == "__main__":
    main()
