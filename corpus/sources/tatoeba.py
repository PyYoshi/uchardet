# SPDX-License-Identifier: MIT
"""Capture a bounded Tatoeba CC0 snapshot, then validate and ingest offline."""

from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MAX_COMPRESSED_BYTES = 2 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
SOURCE_URL = "https://tatoeba.org/en/downloads"
LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
ORIGIN = "tatoeba:cc0-pilot"
LANGUAGES = {"fra": ("fr", "cp1252"), "rus": ("ru", "cp1251")}
FORMAT = "tatoeba-cc0-tsv-4-columns-v1"


def official_url(language: str) -> str:
    if language not in LANGUAGES:
        raise ValueError("only fra/rus official CC0 exports are permitted")
    return f"https://downloads.tatoeba.org/exports/per_language/{language}/{language}_sentences_CC0.tsv.bz2"


def parse_sentences(payload: bytes, language: str) -> list[dict]:
    official_url(language)
    text = payload.decode("utf-8", errors="strict")
    if "\r" in text:
        raise ValueError("expected LF-only CC0 export")
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    rows, seen = [], set()
    for line in lines:
        fields = line.split("\t")
        if len(fields) != 4:
            raise ValueError("expected four CC0 TSV columns")
        sentence_id, row_language, sentence, metadata = fields
        if (
            not re.fullmatch(r"[1-9][0-9]*", sentence_id)
            or row_language != language
            or not sentence
        ):
            raise ValueError("invalid CC0 sentence ID/language/text")
        number = int(sentence_id)
        if number in seen:
            raise ValueError("duplicate CC0 sentence ID")
        seen.add(number)
        rows.append(dict(id=number, text=sentence, export_metadata_raw=metadata))
    if not rows:
        raise ValueError("empty CC0 export")
    return rows


def check_timestamp(value: str) -> None:
    captured = datetime.fromisoformat(value)
    if captured.tzinfo is None or captured.utcoffset().total_seconds() != 0:
        raise ValueError("snapshot capture time must be UTC")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def serialized(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def decompress(data: bytes) -> bytes:
    if not data or len(data) > MAX_COMPRESSED_BYTES:
        raise ValueError("compressed snapshot must be nonempty and at most 2 MiB")
    decoder = bz2.BZ2Decompressor()
    payload = decoder.decompress(data, max_length=MAX_UNCOMPRESSED_BYTES + 1)
    if len(payload) > MAX_UNCOMPRESSED_BYTES:
        raise ValueError("expanded snapshot exceeds 20 MiB")
    if not decoder.eof or decoder.unused_data:
        raise ValueError("expected one complete bzip2 stream without trailing bytes")
    return payload


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Tatoeba snapshot redirects are not allowed")


def new_artifacts(output: Path, files: dict[str, bytes]) -> None:
    # No update-in-place, including interrupted captures: choose a fresh destination.
    output.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)


def checked_read(path: Path, limit: int) -> bytes:
    if path.stat().st_size > limit:
        raise ValueError("cached artifact exceeds pilot budget")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("cached artifact exceeds pilot budget")
    return data


def capture(language: str, output: Path) -> dict:
    url = official_url(language)
    if output.exists():
        raise ValueError("capture destination already exists; never overwrite a snapshot")
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
    with opener.open(request, timeout=30) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError("unexpected snapshot response")
        if response.headers.get("Content-Encoding", "identity") != "identity":
            raise ValueError("unexpected HTTP content encoding")
        compressed = response.read(MAX_COMPRESSED_BYTES + 1)
        last_modified = response.headers.get("Last-Modified")
    return store_snapshot(
        language,
        compressed,
        output,
        datetime.now(timezone.utc).isoformat(),
        "direct-https",
        last_modified,
    )


def store_snapshot(
    language: str,
    compressed: bytes,
    output: Path,
    captured_at: str,
    capture_method: str,
    last_modified: str | None,
) -> dict:
    check_timestamp(captured_at)
    payload = decompress(compressed)
    rows = parse_sentences(payload, language)
    snapshot = dict(
        snapshot_version=1,
        format=FORMAT,
        language=language,
        download_url=official_url(language),
        source_url=SOURCE_URL,
        license="CC0-1.0",
        license_url=LICENSE_URL,
        captured_at=captured_at,
        capture_method=capture_method,
        http_last_modified_raw=last_modified,
        compressed_sha256=digest(compressed),
        compressed_bytes=len(compressed),
        uncompressed_sha256=digest(payload),
        uncompressed_bytes=len(payload),
        sentence_count=len(rows),
    )
    new_artifacts(
        output,
        {
            "archive.tsv.bz2": compressed,
            "sentences.tsv": payload,
            "snapshot.json": serialized(snapshot),
        },
    )
    return snapshot


def import_cache(
    language: str,
    archive: Path,
    output: Path,
    *,
    captured_at: str,
    expected_sha256: str,
    last_modified: str | None = None,
) -> dict:
    """Import operator-attested official bytes without requesting any URL."""
    official_url(language)
    if output.exists():
        raise ValueError("snapshot destination already exists; never overwrite a snapshot")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("expected SHA-256 must be a lowercase hex digest")
    compressed = checked_read(archive, MAX_COMPRESSED_BYTES)
    if digest(compressed) != expected_sha256:
        raise ValueError("imported archive hash mismatch")
    return store_snapshot(
        language, compressed, output, captured_at, "operator-import", last_modified
    )


def validate(snapshot_root: Path) -> tuple[dict, list[dict]]:
    snapshot = json.loads(checked_read(snapshot_root / "snapshot.json", 64 * 1024))
    if snapshot.get("snapshot_version") != 1 or snapshot.get("format") != FORMAT:
        raise ValueError("unsupported snapshot version")
    if (
        snapshot.get("download_url") != official_url(snapshot.get("language"))
        or snapshot.get("source_url") != SOURCE_URL
        or snapshot.get("license") != "CC0-1.0"
        or snapshot.get("license_url") != LICENSE_URL
    ):
        raise ValueError("snapshot source/license metadata mismatch")
    if snapshot.get("capture_method") not in ("direct-https", "operator-import"):
        raise ValueError("invalid snapshot capture method")
    check_timestamp(snapshot["captured_at"])
    compressed = checked_read(snapshot_root / "archive.tsv.bz2", MAX_COMPRESSED_BYTES)
    payload = checked_read(snapshot_root / "sentences.tsv", MAX_UNCOMPRESSED_BYTES)
    for prefix, data in (("compressed", compressed), ("uncompressed", payload)):
        if (
            type(snapshot.get(f"{prefix}_bytes")) is not int
            or snapshot[f"{prefix}_bytes"] != len(data)
            or snapshot.get(f"{prefix}_sha256") != digest(data)
        ):
            raise ValueError("snapshot size/hash mismatch")
    if decompress(compressed) != payload:
        raise ValueError("cached expanded content differs from archive")
    rows = parse_sentences(payload, snapshot["language"])
    if snapshot.get("sentence_count") != len(rows):
        raise ValueError("snapshot sentence count mismatch")
    return snapshot, rows


def ingest(snapshot_root: Path, output: Path, limit: int = 200) -> dict:
    if type(limit) is not int or not 1 <= limit <= 2000:
        raise ValueError("sentence limit must be an integer between 1 and 2000")
    if output.exists():
        raise ValueError("ingest destination already exists; choose a fresh directory")
    snapshot, rows = validate(snapshot_root)
    language, legacy_encoding = LANGUAGES[snapshot["language"]]
    selected = sorted(rows, key=lambda row: row["id"])[:limit]
    sources, files = [], {}
    for row in selected:
        source_id = f"tatoeba-{snapshot['language']}-{row['id']}"
        path = f"texts/{source_id}.txt"
        data = row["text"].encode("utf-8", errors="strict")
        files[path] = data
        sources.append(
            dict(
                id=source_id,
                path=path,
                language=language,
                license="CC0-1.0",
                license_reference=LICENSE_URL,
                revision=snapshot["compressed_sha256"],
                origin=ORIGIN,
                kind="natural",
                sha256=digest(data),
                split="validation",
                source_url=f"https://tatoeba.org/en/sentences/show/{row['id']}",
                tatoeba_sentence_id=row["id"],
                tatoeba_language=snapshot["language"],
                export_metadata_raw=row["export_metadata_raw"],
                snapshot_download_url=snapshot["download_url"],
                snapshot_uncompressed_sha256=snapshot["uncompressed_sha256"],
                snapshot_captured_at=snapshot["captured_at"],
            )
        )
    config = dict(
        sources=sources,
        encodings=["utf-8", legacy_encoding],
        formats=["text"],
        boundaries=["complete"],
        byte_limits=[None, 64, 1024],
    )
    report = dict(
        ingestion_version=1,
        snapshot=snapshot,
        selection="ascending-numeric-sentence-id",
        requested_limit=limit,
        available_sentences=len(rows),
        selected_sentences=len(selected),
        selected_ids=[row["id"] for row in selected],
        split="validation",
        origin=ORIGIN,
        bias="Lowest numeric IDs only; not random, representative or independent evaluation.",
        legacy_representability_filter=False,
        required_generation_failure_policy="record-and-continue",
    )
    files["config.json"] = serialized(config)
    files["ingestion-report.json"] = serialized(report)
    new_artifacts(output, files)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    cap = commands.add_parser("capture", help="explicit network capture into a fresh directory")
    cap.add_argument("language", choices=sorted(LANGUAGES))
    cap.add_argument("output", type=Path)
    check = commands.add_parser("validate", help="offline snapshot validation")
    check.add_argument("snapshot", type=Path)
    local = commands.add_parser(
        "import-cache", help="offline import of operator-attested official archive"
    )
    local.add_argument("language", choices=sorted(LANGUAGES))
    local.add_argument("archive", type=Path)
    local.add_argument("output", type=Path)
    local.add_argument("--captured-at", required=True)
    local.add_argument("--sha256", required=True)
    local.add_argument("--last-modified")
    convert = commands.add_parser("ingest", help="offline validation-only corpus config")
    convert.add_argument("snapshot", type=Path)
    convert.add_argument("output", type=Path)
    convert.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    if args.command == "capture":
        result = capture(args.language, args.output)
    elif args.command == "validate":
        result, _ = validate(args.snapshot)
    elif args.command == "import-cache":
        result = import_cache(
            args.language,
            args.archive,
            args.output,
            captured_at=args.captured_at,
            expected_sha256=args.sha256,
            last_modified=args.last_modified,
        )
    else:
        result = ingest(args.snapshot, args.output, args.limit)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
