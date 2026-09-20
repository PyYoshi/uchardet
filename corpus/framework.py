# SPDX-License-Identifier: MIT
"""Offline, deterministic corpus generation. No third-party dependencies."""

from __future__ import annotations

import argparse
import codecs
import hashlib
import html
import itertools
import json
import platform
import re
from pathlib import Path

SPLITS = {"training", "tuning", "validation", "independent"}
ID = re.compile(r"[A-Za-z0-9_-]+\Z")
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


class NonRoundTripError(ValueError):
    """A valid codec cannot preserve this source's Unicode content."""


def generation_config(config: dict) -> dict:
    """Validate every dimension before processing potentially unencodable text."""
    dimensions = {}
    for name, default in (("encodings", None), ("formats", ["text"]),
                          ("boundaries", ["complete"]), ("byte_limits", [None])):
        values = config.get(name, default)
        if not isinstance(values, list) or not values:
            raise ValueError(f"{name} must be a nonempty list")
        normalized = []
        for value in values:
            if name == "encodings":
                if not isinstance(value, str):
                    raise ValueError("encoding must be a string")
                codec = codecs.lookup(value)
                if not codec._is_text_encoding:
                    raise ValueError("encoding must be a text codec")
                value = codec.name
            elif name == "formats":
                if value not in ("text", "html-clean", "html-declared", "html-mismatched"):
                    raise ValueError("unknown format")
            elif name == "boundaries":
                if value not in ("complete", "truncated"):
                    raise ValueError("invalid boundary mode")
            elif value is not None and (type(value) is not int or value <= 0):
                raise ValueError("byte limit must be positive integer or null")
            if value in normalized:
                raise ValueError("duplicate variant dimension")
            normalized.append(value)
        dimensions[name] = normalized
    return dimensions


def attempts(sources: list[dict], dimensions: dict):
    for source, encoding, format, boundary, limit in itertools.product(
            sources, dimensions["encodings"], dimensions["formats"],
            dimensions["boundaries"], dimensions["byte_limits"]):
        yield dict(source_id=source["id"], encoding=encoding, format=format,
                   boundary=boundary, byte_limit=limit)


def variant_id(variant: dict) -> str:
    return "-".join(str(variant[key]) for key in
                    ("source_id", "encoding", "format", "boundary", "byte_limit"))


def ground_truth(payload: str, encoding: str, encoded: bytes, boundary: str) -> dict:
    truncated = boundary == "truncated" and len(encoded) < len(payload.encode(encoding, errors="strict"))
    return {"provenance": "strict-source-reencoding",
            "certainty": "byte-truncated" if truncated else "strict-roundtrip"}


def audit_splits(manifests: list[dict]) -> dict:
    """Metadata-only audit; never reads samples or invokes any detector."""
    groups = {"sha256": {}, "origin": {}}
    count = 0
    for manifest in manifests:
        if manifest.get("schema_version") != 1 or manifest.get("content_hash") != content_hash(manifest):
            raise ValueError("invalid manifest schema or content hash")
        check_source_groups(manifest["sources"])
        for source in manifest["sources"]:
            count += 1
            for field, seen in groups.items():
                key = source[field]
                if key in seen and seen[key] != source["split"]:
                    raise ValueError(f"cross-manifest source split leakage ({field}: {key})")
                seen[key] = source["split"]
    return {"manifests": len(manifests), "source_records": count, "split_leakage": False}


def audit_manifests(paths: list[Path]) -> dict:
    """Read only manifests, without reading their referenced sources or samples."""
    return audit_splits([json.loads(path.read_text(encoding="utf-8")) for path in paths])


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
    if not isinstance(source, dict):
        raise ValueError("source must be an object")
    required(source, ("id", "path", "language", "license", "license_reference",
                      "revision", "origin", "sha256", "split", "kind"))
    if not ID.fullmatch(source["id"]) or source["split"] not in SPLITS:
        raise ValueError("invalid source id or split")
    if source["kind"] not in {"synthetic", "natural"}:
        raise ValueError("invalid source kind")
    if not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]):
        raise ValueError("invalid source sha256")


def check_source_groups(sources: list[dict]) -> None:
    if not isinstance(sources, list):
        raise ValueError("sources must be a list")
    ids, hashes, origins = set(), {}, {}
    for source in sources:
        check_source(source)
        if source["id"] in ids:
            raise ValueError("duplicate source id")
        ids.add(source["id"])
        for groups, key in ((hashes, source["sha256"]), (origins, source["origin"])):
            if key in groups and groups[key] != source["split"]:
                raise ValueError("source split leakage")
            groups[key] = source["split"]


def encode_variant(text: str, encoding: str, limit: int | None,
                   boundary: str) -> tuple[bytes, int | None]:
    full = text.encode(encoding, errors="strict")
    try:
        decoded = full.decode(encoding, errors="strict")
    except UnicodeDecodeError as error:
        raise NonRoundTripError("encoded source cannot decode strictly") from error
    if decoded != text:
        raise NonRoundTripError("source cannot round-trip in requested encoding")
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
        if "ground_truth" in sample or "generation_report" in manifest:
            if sample.get("ground_truth") != ground_truth(payload, sample["encoding"], data, sample["boundary"]):
                raise ValueError("ground truth metadata mismatch")
    if "generation_report" in manifest:
        validate_report(manifest, sources)


def validate_report(manifest: dict, sources: dict) -> None:
    report = manifest["generation_report"]
    dimensions = generation_config(report["dimensions"])
    if dimensions != report["dimensions"]:
        raise ValueError("report dimensions must be canonical")
    if report.get("failure_policy") not in ("fail-fast", "record-and-continue"):
        raise ValueError("invalid failure policy")
    records = report["attempts"]
    expected_variants = list(attempts(manifest["sources"], dimensions))
    if len(records) != len(expected_variants):
        raise ValueError("attempt coverage mismatch")
    samples = {sample["id"]: sample for sample in manifest["samples"]}
    successful = set()
    for record, variant in zip(records, expected_variants):
        source, text = sources[variant["source_id"]]
        payload, _ = render(text, variant["format"], variant["encoding"])
        try:
            encode_variant(payload, variant["encoding"], variant["byte_limit"], variant["boundary"])
        except (UnicodeEncodeError, NonRoundTripError) as error:
            reason = "unencodable" if isinstance(error, UnicodeEncodeError) else "non-roundtrip"
            expected = dict(variant, status="skipped", reason=reason)
            if report["failure_policy"] != "record-and-continue":
                raise ValueError("skipped attempt in fail-fast report")
        else:
            sample_id = variant_id(variant)
            expected = dict(variant, status="success", sample_id=sample_id)
            sample = samples.get(sample_id)
            if sample is None or any(sample.get(key) != value for key, value in variant.items()):
                raise ValueError("successful attempt sample mismatch")
            successful.add(sample_id)
        if record != expected:
            raise ValueError("attempt outcome mismatch")
    if successful != set(samples):
        raise ValueError("unaccounted sample")
    counts = dict(attempted=len(records), successful=len(successful), skipped=len(records) - len(successful))
    if report.get("counts") != counts:
        raise ValueError("attempt counts mismatch")


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


def generate(config: dict, source_root: Path, output: Path, *,
             failure_policy: str = "fail-fast") -> dict:
    if output.exists():
        raise ValueError("output must not exist (never overwrite corpus artifacts)")
    if failure_policy not in ("fail-fast", "record-and-continue"):
        raise ValueError("invalid failure policy")
    dimensions = generation_config(config)
    sources, samples, files, records = [], [], {}, []
    check_source_groups(config["sources"])
    artifact_bytes = 0
    for original in config["sources"]:
        check_source(original)
        source_path = safe_path(source_root, original["path"])
        if source_path.stat().st_size > MAX_ARTIFACT_BYTES - artifact_bytes:
            raise ValueError("v1 artifact budget exceeded (64 MiB)")
        data = source_path.read_bytes()
        artifact_bytes += len(data)
        if artifact_bytes > MAX_ARTIFACT_BYTES:
            raise ValueError("v1 artifact budget exceeded (64 MiB)")
        if digest(data) != original["sha256"]:
            raise ValueError("source hash mismatch")
        text = data.decode("utf-8", errors="strict")
        source = dict(original, path=f"sources/{original['id']}.txt", byte_length=len(data), character_length=len(text))
        sources.append(source)
        files[source["path"]] = data
        for encoding in dimensions["encodings"]:
            encoding = codecs.lookup(encoding).name
            for format in dimensions["formats"]:
                payload, declaration = render(text, format, encoding)
                for boundary in dimensions["boundaries"]:
                    for limit in dimensions["byte_limits"]:
                        variant = dict(source_id=source["id"], encoding=encoding, format=format,
                                       boundary=boundary, byte_limit=limit)
                        try:
                            encoded, chars = encode_variant(payload, encoding, limit, boundary)
                        except (UnicodeEncodeError, NonRoundTripError) as error:
                            if failure_policy == "fail-fast":
                                raise
                            reason = "unencodable" if isinstance(error, UnicodeEncodeError) else "non-roundtrip"
                            records.append(dict(variant, status="skipped", reason=reason))
                            continue
                        artifact_bytes += len(encoded)
                        if artifact_bytes > MAX_ARTIFACT_BYTES:
                            raise ValueError("v1 artifact budget exceeded (64 MiB)")
                        sample_id = f"{source['id']}-{encoding}-{format}-{boundary}-{limit}"
                        sample = dict(id=sample_id, path=f"samples/{sample_id}.bin", source_id=source["id"],
                                      split=source["split"], encoding=encoding, format=format,
                                      declared_encoding=declaration, byte_limit=limit, boundary=boundary,
                                      byte_length=len(encoded), character_length=chars, sha256=digest(encoded),
                                      encoder="python-codecs", encoder_version=f"{platform.python_implementation()} {platform.python_version()}")
                        sample["ground_truth"] = ground_truth(payload, encoding, encoded, boundary)
                        records.append(dict(variant, status="success", sample_id=sample_id))
                        samples.append(sample)
                        if sample["path"] in files:
                            raise ValueError("duplicate variant")
                        files[sample["path"]] = encoded
    manifest = dict(schema_version=1, sources=sources, samples=samples)
    manifest["generation_report"] = dict(dimensions=dimensions, failure_policy=failure_policy,
        attempts=records, counts=dict(attempted=len(records), successful=len(samples),
                                     skipped=len(records) - len(samples)))
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
    gen.add_argument("--failure-policy", choices=("fail-fast", "record-and-continue"), default="fail-fast")
    check = commands.add_parser("validate")
    check.add_argument("manifest", type=Path)
    audit = commands.add_parser("audit-splits", help="metadata-only cross-manifest split audit")
    audit.add_argument("manifests", type=Path, nargs="+")
    args = parser.parse_args()
    if args.command == "generate":
        generate(json.loads(args.config.read_text(encoding="utf-8")), args.config.parent, args.output,
                 failure_policy=args.failure_policy)
    elif args.command == "audit-splits":
        print(json.dumps(audit_manifests(args.manifests), sort_keys=True))
    else:
        validate(json.loads(args.manifest.read_text(encoding="utf-8")), args.manifest.parent)


if __name__ == "__main__":
    main()
