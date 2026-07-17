from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

IGNORED_FILENAMES = {".DS_Store"}


@dataclass(frozen=True)
class ScannedFile:
    absolute_path: Path
    relative_path: str
    size_bytes: int
    modified_at: float
    knowledge_source: str


@dataclass(frozen=True)
class ExcludedEntry:
    """A file skipped by policy (dotfile, ignored filename). Not a failure."""

    relative_path: str
    reason: str


@dataclass(frozen=True)
class ScanFailure:
    """A file or directory that could not be scanned (e.g. broken symlink,
    permission error, an unreadable directory, or removal mid-walk).
    Distinct from a policy exclusion. For a directory failure, `relative_path`
    identifies the directory itself; its contents are never visited and are
    therefore not individually counted."""

    relative_path: str
    reason: str
    error_type: str


@dataclass(frozen=True)
class ScanReport:
    eligible: list[ScannedFile] = field(default_factory=list)
    excluded: list[ExcludedEntry] = field(default_factory=list)
    failed: list[ScanFailure] = field(default_factory=list)


def _exclusion_reason(filename: str) -> str | None:
    if filename in IGNORED_FILENAMES:
        return "ignored_filename"
    if filename.startswith("."):
        return "dotfile"
    return None


def _walk(
    root: Path,
) -> Iterator[tuple[ScannedFile | None, ExcludedEntry | None, ScanFailure | None]]:
    root = Path(root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Scan root does not exist: {root}")

    # os.walk silently drops a directory it cannot list (permission error,
    # removal mid-walk) unless given `onerror`: it calls the callback and
    # then simply never yields a tuple for that directory or descends into
    # it. `onerror` fires synchronously from inside the internal walk
    # generator, ahead of whatever tuple (if any) `next()` returns next, so
    # queuing failures here and draining the queue around each `next()` call
    # below reports them in the same deterministic, traversal order as
    # everything else.
    pending_dir_failures: list[ScanFailure] = []

    def _record_dir_error(error: OSError) -> None:
        failed_path = Path(error.filename) if error.filename else root
        try:
            relative_path = failed_path.relative_to(root)
        except ValueError:
            relative_path = failed_path
        pending_dir_failures.append(
            ScanFailure(
                relative_path=str(relative_path),
                reason=str(error),
                error_type=type(error).__name__,
            )
        )

    walker = os.walk(root, onerror=_record_dir_error)

    while True:
        try:
            dirpath, dirnames, filenames = next(walker)
        except StopIteration:
            break

        while pending_dir_failures:
            yield None, None, pending_dir_failures.pop(0)

        # Dot-directories are pruned from traversal entirely (as in V1); their
        # contents are never visited by os.walk and are therefore not counted
        # individually as discovered/excluded/failed.
        dirnames[:] = sorted(name for name in dirnames if not name.startswith("."))

        for filename in sorted(filenames):
            absolute_path = Path(dirpath) / filename
            relative_path = absolute_path.relative_to(root)

            reason = _exclusion_reason(filename)
            if reason is not None:
                yield None, ExcludedEntry(relative_path=str(relative_path), reason=reason), None
                continue

            try:
                stat_result = absolute_path.stat()
            except OSError as exc:
                yield None, None, ScanFailure(
                    relative_path=str(relative_path),
                    reason=str(exc),
                    error_type=type(exc).__name__,
                )
                continue

            yield (
                ScannedFile(
                    absolute_path=absolute_path,
                    relative_path=str(relative_path),
                    size_bytes=stat_result.st_size,
                    modified_at=stat_result.st_mtime,
                    knowledge_source=relative_path.parts[0],
                ),
                None,
                None,
            )

    while pending_dir_failures:
        yield None, None, pending_dir_failures.pop(0)


def scan(root: Path) -> Iterator[ScannedFile]:
    """Yield eligible files only, exactly as V1 did (policy exclusions and
    stat failures are silently skipped). Preserved for backward compatibility."""
    for scanned, _, _ in _walk(root):
        if scanned is not None:
            yield scanned


def scan_with_report(root: Path) -> ScanReport:
    """Walk `root` and separate results into eligible / excluded-by-policy /
    failed-to-stat, so callers can report discovered vs eligible vs excluded
    metrics without conflating policy exclusions with read failures."""
    report = ScanReport()
    for scanned, excluded, failure in _walk(root):
        if scanned is not None:
            report.eligible.append(scanned)
        elif excluded is not None:
            report.excluded.append(excluded)
        else:
            report.failed.append(failure)
    return report
