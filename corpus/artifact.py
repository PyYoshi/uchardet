# SPDX-License-Identifier: MIT
"""Publish one complete artifact without replacing an existing destination."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile


def existing_matches(path: Path, data: bytes) -> bool:
    try:
        previous = path.read_bytes()
    except FileNotFoundError:
        return False
    if previous != data:
        raise ValueError("refusing to overwrite different artifact")
    return True


def write_idempotent(path: Path, data: bytes) -> None:
    if existing_matches(path, data):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # Same filesystem: linking publishes the completed file, exclusively.
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            # A concurrent writer may have published exactly the same artifact.
            if not existing_matches(path, data):
                raise ValueError("destination disappeared during publication") from None
    finally:
        temporary.unlink(missing_ok=True)
