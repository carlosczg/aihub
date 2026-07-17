from __future__ import annotations

import json
import secrets
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .diff import ClassificationResult
from .io_utils import stage_text
from .metadata import DocumentMetadata
from .scanner import ExcludedEntry

DOCUMENT_MANIFEST_FILENAME = "document_manifest.jsonl"
RUN_METADATA_FILENAME = "manifest_run_metadata.json"
RUN_HISTORY_SUBDIR = "runs"
MANIFEST_SCHEMA_VERSION = 2

REQUIRED_DOCUMENT_FIELDS = {
    "relative_path",
    "file_name",
    "extension",
    "size_bytes",
    "modified_at",
    "knowledge_source",
    "sha256",
    "mime_type",
}

REQUIRED_METRICS_FIELDS = {
    "discovered",
    "eligible",
    "excluded",
    "processed",
    "new",
    "modified",
    "unchanged",
    "deleted",
    "failed",
    "hashes_recomputed",
    "hashes_reused",
    "duration_seconds",
}

REQUIRED_RUN_METADATA_FIELDS = {
    "schema_version",
    "run_id",
    "mode",
    "manifest_status",
    "started_at",
    "generated_at",
    "exit_code",
    "metrics",
}

REQUIRED_RUN_HISTORY_FIELDS = {
    "schema_version",
    "run_id",
    "metrics",
}


class ManifestCorruptError(RuntimeError):
    def __init__(self, path: Path, reason: str):
        super().__init__(f"Previous manifest at '{path}' is corrupt or unreadable: {reason}")
        self.path = path
        self.reason = reason


@dataclass(frozen=True)
class PreviousManifest:
    entries: dict[str, DocumentMetadata]
    is_legacy: bool = False


def sort_documents(entries) -> list[DocumentMetadata]:
    return sorted(entries, key=lambda entry: entry.relative_path)


def generate_run_id() -> str:
    now = datetime.now(timezone.utc)
    return f"{now:%Y%m%dT%H%M%S.%f}Z-{secrets.token_hex(2)}"


def unique_run_id(runs_dir: Path, attempts: int = 10) -> str:
    for _ in range(attempts):
        run_id = generate_run_id()
        if not (runs_dir / f"run_{run_id}.json").exists():
            return run_id
    raise RuntimeError("Unable to generate a unique run id after multiple attempts")


def load_previous_manifest(manifest_path: Path, *, migration_timestamp: str) -> PreviousManifest:
    """Load the current-state manifest written by the previous run.

    A missing file is a valid state (first full run). A present-but-corrupt
    file raises ManifestCorruptError rather than being silently treated as
    absent -- callers must decide explicitly (via --full) whether to recover.
    """
    if not manifest_path.is_file():
        return PreviousManifest(entries={}, is_legacy=False)

    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestCorruptError(manifest_path, f"unreadable: {exc}") from exc

    entries: dict[str, DocumentMetadata] = {}
    is_legacy = False

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ManifestCorruptError(
                manifest_path, f"invalid JSON on line {line_number}: {exc}"
            ) from exc

        if not isinstance(record, dict):
            raise ManifestCorruptError(
                manifest_path, f"line {line_number} is not a JSON object"
            )

        missing = REQUIRED_DOCUMENT_FIELDS - record.keys()
        if missing:
            raise ManifestCorruptError(
                manifest_path, f"line {line_number} missing fields: {sorted(missing)}"
            )

        relative_path = record["relative_path"]
        if relative_path in entries:
            raise ManifestCorruptError(
                manifest_path,
                f"duplicate relative_path '{relative_path}' on line {line_number}",
            )

        if "first_seen_at" not in record or "last_verified_at" not in record:
            is_legacy = True

        entries[relative_path] = DocumentMetadata(
            relative_path=relative_path,
            file_name=record["file_name"],
            extension=record["extension"],
            size_bytes=record["size_bytes"],
            modified_at=record["modified_at"],
            knowledge_source=record["knowledge_source"],
            sha256=record["sha256"],
            mime_type=record.get("mime_type"),
            first_seen_at=record.get("first_seen_at") or migration_timestamp,
            last_verified_at=record.get("last_verified_at") or migration_timestamp,
        )

    return PreviousManifest(entries=entries, is_legacy=is_legacy)


def backup_corrupt_manifest(manifest_path: Path, run_id: str) -> Path:
    """Copy (not move) the invalid manifest aside for forensics before a
    --full recovery run potentially replaces it."""
    backup_path = manifest_path.with_name(f"{manifest_path.name}.corrupt-{run_id}")
    shutil.copy2(manifest_path, backup_path)
    return backup_path


def _bounded_list(items: list, limit: int = 500) -> list:
    if len(items) <= limit:
        return items
    return items[:limit] + [f"... (+{len(items) - limit} more)"]


def build_run_history_payload(
    *,
    run_id: str,
    mode: str,
    manifest_status: str,
    started_at: str,
    generated_at: str,
    exit_code: int,
    metrics: dict,
    classification: ClassificationResult,
    excluded: list[ExcludedEntry],
) -> dict:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "mode": mode,
        "manifest_status": manifest_status,
        "started_at": started_at,
        "generated_at": generated_at,
        "exit_code": exit_code,
        "metrics": metrics,
        "new": _bounded_list(classification.new),
        "modified": _bounded_list(classification.modified),
        "deleted": _bounded_list(classification.deleted),
        "excluded": _bounded_list(
            [{"relative_path": item.relative_path, "reason": item.reason} for item in excluded]
        ),
        "failed": _bounded_list([asdict(item) for item in classification.failed]),
    }


def build_run_metadata_payload(
    *,
    run_id: str,
    previous_run_id: str | None,
    mode: str,
    manifest_status: str,
    started_at: str,
    generated_at: str,
    exit_code: int,
    metrics: dict,
) -> dict:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "previous_run_id": previous_run_id,
        "mode": mode,
        "manifest_status": manifest_status,
        "started_at": started_at,
        "generated_at": generated_at,
        "exit_code": exit_code,
        "metrics": metrics,
    }


def _validate_document_manifest_content(content: str, *, expected_count: int) -> None:
    lines = content.splitlines() if content else []
    if len(lines) != expected_count:
        raise ValueError(
            f"document manifest line count mismatch: expected {expected_count}, got {len(lines)}"
        )

    previous_key: str | None = None
    seen: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        record = json.loads(line)
        missing = REQUIRED_DOCUMENT_FIELDS - record.keys()
        if missing:
            raise ValueError(f"line {line_number} missing fields: {sorted(missing)}")

        key = record["relative_path"]
        if key in seen:
            raise ValueError(f"duplicate relative_path in staged manifest: {key}")
        seen.add(key)

        if previous_key is not None and key < previous_key:
            raise ValueError("staged document manifest is not sorted by relative_path")
        previous_key = key


def _validate_run_metadata_content(content: str) -> None:
    data = json.loads(content)
    missing = REQUIRED_RUN_METADATA_FIELDS - data.keys()
    if missing:
        raise ValueError(f"run metadata missing fields: {sorted(missing)}")

    metrics = data["metrics"]
    missing_metrics = REQUIRED_METRICS_FIELDS - metrics.keys()
    if missing_metrics:
        raise ValueError(f"run metadata metrics missing fields: {sorted(missing_metrics)}")

    if metrics["discovered"] != metrics["eligible"] + metrics["excluded"]:
        raise ValueError("metrics invariant violated: discovered != eligible + excluded")
    if metrics["eligible"] != metrics["processed"] + metrics["failed"]:
        raise ValueError("metrics invariant violated: eligible != processed + failed")
    if metrics["processed"] != metrics["new"] + metrics["modified"] + metrics["unchanged"]:
        raise ValueError("metrics invariant violated: processed != new + modified + unchanged")
    if metrics["hashes_recomputed"] + metrics["hashes_reused"] != metrics["processed"]:
        raise ValueError(
            "metrics invariant violated: hashes_recomputed + hashes_reused != processed"
        )


def _validate_run_history_content(content: str) -> None:
    data = json.loads(content)
    missing = REQUIRED_RUN_HISTORY_FIELDS - data.keys()
    if missing:
        raise ValueError(f"run history missing fields: {sorted(missing)}")


def stage_and_publish_run(
    *,
    indexes_dir: Path,
    document_entries: dict[str, DocumentMetadata],
    run_history_payload: dict,
    run_metadata_payload: dict,
    run_id: str,
) -> tuple[Path, Path, Path]:
    """Stage all three run artifacts as temp files, validate every one of
    them, and only then publish. Publish order is history -> document
    manifest -> run metadata (the pointer to the latest committed run is
    updated last). If staging or validation of any artifact fails, none of
    the three final targets are changed and all temp files are removed.

    Filesystem operations across multiple files are not fully transactional
    (a crash between two os.replace() calls can still leave the three
    artifacts momentarily inconsistent with each other), but this staging
    and ordering minimizes the window and the severity of any inconsistent
    visible state: the immutable, self-contained history file can safely
    appear before anything else; the document manifest (the file future runs
    diff against) is only replaced once known-valid; and the "latest run"
    pointer is only flipped after the state it points to already exists.
    """
    document_manifest_path = indexes_dir / DOCUMENT_MANIFEST_FILENAME
    run_metadata_path = indexes_dir / RUN_METADATA_FILENAME
    run_history_path = indexes_dir / RUN_HISTORY_SUBDIR / f"run_{run_id}.json"

    sorted_entries = sort_documents(document_entries.values())
    manifest_lines = [
        json.dumps(asdict(entry), sort_keys=True, ensure_ascii=False) for entry in sorted_entries
    ]
    manifest_content = ("\n".join(manifest_lines) + "\n") if manifest_lines else ""

    run_history_content = (
        json.dumps(run_history_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    run_metadata_content = (
        json.dumps(run_metadata_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )

    staged_artifacts = []
    try:
        staged_artifacts.append(
            stage_text(run_history_path, run_history_content, _validate_run_history_content)
        )
        staged_artifacts.append(
            stage_text(
                document_manifest_path,
                manifest_content,
                lambda content: _validate_document_manifest_content(
                    content, expected_count=len(sorted_entries)
                ),
            )
        )
        staged_artifacts.append(
            stage_text(run_metadata_path, run_metadata_content, _validate_run_metadata_content)
        )
    except Exception:
        for artifact in staged_artifacts:
            artifact.discard()
        raise

    for artifact in staged_artifacts:
        artifact.publish()

    return document_manifest_path, run_metadata_path, run_history_path
