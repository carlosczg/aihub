from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .metadata import DocumentMetadata, build_document_metadata, compute_hash, modified_at_iso
from .scanner import ScanFailure, ScannedFile


@dataclass(frozen=True)
class FailedFile:
    relative_path: str
    reason: str
    error_type: str
    previous_entry_preserved: bool


@dataclass(frozen=True)
class ClassificationResult:
    manifest_entries: dict[str, DocumentMetadata]
    new: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    failed: list[FailedFile] = field(default_factory=list)
    hashes_recomputed: int = 0
    hashes_reused: int = 0


def classify(
    eligible: list[ScannedFile],
    previous: dict[str, DocumentMetadata],
    *,
    force_full: bool,
    run_timestamp: str | None = None,
    scan_failures: list[ScanFailure] = (),
) -> ClassificationResult:
    """Compare `eligible` (this run's stat results) against `previous` (the
    prior manifest, keyed by relative_path -- the identifier is path-stable,
    not rename-stable: a move/rename surfaces as one delete + one new entry).

    `force_full` forces every eligible file's hash to be recomputed, but
    classification (new/modified/unchanged) is still derived by comparing
    against `previous` -- it never treats an existing path as unconditionally
    new.
    """
    run_timestamp = run_timestamp or datetime.now(timezone.utc).isoformat()

    new: list[str] = []
    modified: list[str] = []
    unchanged: list[str] = []
    failed: list[FailedFile] = []
    hashes_recomputed = 0
    hashes_reused = 0
    manifest_entries: dict[str, DocumentMetadata] = {}
    seen_paths: set[str] = set()

    for failure in scan_failures:
        seen_paths.add(failure.relative_path)
        prev = previous.get(failure.relative_path)
        failed.append(
            FailedFile(
                relative_path=failure.relative_path,
                reason=failure.reason,
                error_type=failure.error_type,
                previous_entry_preserved=prev is not None,
            )
        )
        if prev is not None:
            manifest_entries[failure.relative_path] = prev

    for scanned in eligible:
        seen_paths.add(scanned.relative_path)
        prev = previous.get(scanned.relative_path)
        try:
            current_modified_at = modified_at_iso(scanned)
            need_hash = (
                force_full
                or prev is None
                or prev.size_bytes != scanned.size_bytes
                or prev.modified_at != current_modified_at
            )

            if need_hash:
                sha256 = compute_hash(scanned.absolute_path)
                hashes_recomputed += 1
            else:
                sha256 = prev.sha256
                hashes_reused += 1

            if prev is None:
                classification = "new"
                first_seen_at = run_timestamp
            elif sha256 == prev.sha256:
                classification = "unchanged"
                first_seen_at = prev.first_seen_at
            else:
                classification = "modified"
                first_seen_at = prev.first_seen_at

            last_verified_at = run_timestamp if need_hash else prev.last_verified_at

            entry = build_document_metadata(
                scanned,
                sha256=sha256,
                first_seen_at=first_seen_at,
                last_verified_at=last_verified_at,
            )
            manifest_entries[scanned.relative_path] = entry

            if classification == "new":
                new.append(scanned.relative_path)
            elif classification == "modified":
                modified.append(scanned.relative_path)
            else:
                unchanged.append(scanned.relative_path)

        except OSError as exc:
            failed.append(
                FailedFile(
                    relative_path=scanned.relative_path,
                    reason=str(exc),
                    error_type=type(exc).__name__,
                    previous_entry_preserved=prev is not None,
                )
            )
            if prev is not None:
                manifest_entries[scanned.relative_path] = prev

    deleted = sorted(path for path in previous if path not in seen_paths)

    return ClassificationResult(
        manifest_entries=manifest_entries,
        new=sorted(new),
        modified=sorted(modified),
        unchanged=sorted(unchanged),
        deleted=deleted,
        failed=failed,
        hashes_recomputed=hashes_recomputed,
        hashes_reused=hashes_reused,
    )
