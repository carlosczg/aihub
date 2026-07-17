from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone

from .scanner import ScannedFile

DEFAULT_HASH_ALGORITHM = "sha256"
_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class DocumentMetadata:
    relative_path: str
    file_name: str
    extension: str
    size_bytes: int
    modified_at: str
    knowledge_source: str
    sha256: str
    mime_type: str | None
    first_seen_at: str
    last_verified_at: str


def compute_hash(path, algorithm: str = DEFAULT_HASH_ALGORITHM) -> str:
    digest = hashlib.new(algorithm)
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def modified_at_iso(scanned_file: ScannedFile) -> str:
    return datetime.fromtimestamp(scanned_file.modified_at, tz=timezone.utc).isoformat()


def build_document_metadata(
    scanned_file: ScannedFile,
    *,
    sha256: str,
    first_seen_at: str,
    last_verified_at: str,
) -> DocumentMetadata:
    """Build a DocumentMetadata record from a precomputed hash, so callers
    that already know the hash (e.g. the incremental diff engine reusing a
    previous run's hash) never trigger a redundant file read."""
    mime_type, _ = mimetypes.guess_type(scanned_file.absolute_path.name)
    return DocumentMetadata(
        relative_path=scanned_file.relative_path,
        file_name=scanned_file.absolute_path.name,
        extension=scanned_file.absolute_path.suffix.lower(),
        size_bytes=scanned_file.size_bytes,
        modified_at=modified_at_iso(scanned_file),
        knowledge_source=scanned_file.knowledge_source,
        sha256=sha256,
        mime_type=mime_type,
        first_seen_at=first_seen_at,
        last_verified_at=last_verified_at,
    )


def extract_metadata(
    scanned_file: ScannedFile,
    *,
    first_seen_at: str | None = None,
    last_verified_at: str | None = None,
) -> DocumentMetadata:
    """Compute the hash internally and build a DocumentMetadata record.

    Kept for standalone/legacy use; the incremental engine in `diff.py` does
    not call this (it decides separately whether a hash needs recomputing).
    """
    now = datetime.now(timezone.utc).isoformat()
    sha256 = compute_hash(scanned_file.absolute_path)
    return build_document_metadata(
        scanned_file,
        sha256=sha256,
        first_seen_at=first_seen_at or now,
        last_verified_at=last_verified_at or now,
    )
