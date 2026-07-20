from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .io_utils import stage_text
from .manifest import unique_run_id  # noqa: F401  (re-exported for callers)

if TYPE_CHECKING:
    from .normalizer_diff import NormalizerClassificationResult

DOCUMENT_NORMALIZER_MANIFEST_FILENAME = "document_normalizer_manifest.jsonl"
NORMALIZER_RUN_METADATA_FILENAME = "normalizer_run_metadata.json"
RUN_HISTORY_SUBDIR = "runs"
CURATED_MANIFEST_SCHEMA_VERSION = 1

REQUIRED_CURATED_FIELDS = {
    "relative_path",
    "knowledge_source",
    "source_extension",
    "source_sha256",
    "converter_id",
    "converter_version",
    "output_relative_path",
    "output_sha256",
    "first_seen_at",
    "last_converted_at",
}

REQUIRED_METRICS_FIELDS = {
    "source_total",
    "text_native",
    "deferred",
    "unsupported",
    "converted_new",
    "converted_stale",
    "converted_stale_converter",
    "unchanged",
    "failed",
    "orphaned",
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
    "failed",
}

REQUIRED_RUN_HISTORY_FIELDS = {
    "schema_version",
    "run_id",
    "metrics",
}


class CuratedManifestCorruptError(RuntimeError):
    def __init__(self, path: Path, reason: str):
        super().__init__(f"Previous curated manifest at '{path}' is corrupt or unreadable: {reason}")
        self.path = path
        self.reason = reason


@dataclass(frozen=True)
class CuratedDocumentMetadata:
    relative_path: str
    knowledge_source: str
    source_extension: str
    source_sha256: str
    converter_id: str
    converter_version: str
    output_relative_path: str
    output_sha256: str
    first_seen_at: str
    last_converted_at: str


@dataclass(frozen=True)
class PreviousCuratedManifest:
    entries: dict[str, CuratedDocumentMetadata] = field(default_factory=dict)


def sort_documents(entries) -> list[CuratedDocumentMetadata]:
    return sorted(entries, key=lambda entry: entry.relative_path)


def load_previous_curated_manifest(manifest_path: Path) -> dict[str, CuratedDocumentMetadata]:
    """Load the curated manifest written by the previous normalizer run.

    A missing file is a valid state (first normalizer run). A present but
    unparseable file raises `CuratedManifestCorruptError` -- there is no
    `--full` recovery path for the curated manifest in V1.2.0; a corrupt
    curated manifest always aborts the run without advancing it.
    """
    if not manifest_path.is_file():
        return {}

    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CuratedManifestCorruptError(manifest_path, f"unreadable: {exc}") from exc

    entries: dict[str, CuratedDocumentMetadata] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CuratedManifestCorruptError(
                manifest_path, f"invalid JSON on line {line_number}: {exc}"
            ) from exc

        if not isinstance(record, dict):
            raise CuratedManifestCorruptError(
                manifest_path, f"line {line_number} is not a JSON object"
            )

        missing = REQUIRED_CURATED_FIELDS - record.keys()
        if missing:
            raise CuratedManifestCorruptError(
                manifest_path, f"line {line_number} missing fields: {sorted(missing)}"
            )

        relative_path = record["relative_path"]
        if relative_path in entries:
            raise CuratedManifestCorruptError(
                manifest_path,
                f"duplicate relative_path '{relative_path}' on line {line_number}",
            )

        entries[relative_path] = CuratedDocumentMetadata(
            relative_path=relative_path,
            knowledge_source=record["knowledge_source"],
            source_extension=record["source_extension"],
            source_sha256=record["source_sha256"],
            converter_id=record["converter_id"],
            converter_version=record["converter_version"],
            output_relative_path=record["output_relative_path"],
            output_sha256=record["output_sha256"],
            first_seen_at=record["first_seen_at"],
            last_converted_at=record["last_converted_at"],
        )

    return entries


def _bounded_list(items: list, limit: int = 500) -> list:
    if len(items) <= limit:
        return items
    return items[:limit] + [f"... (+{len(items) - limit} more)"]


def build_failure_details(classification: "NormalizerClassificationResult") -> list[dict]:
    """The single source of failure detail used by both `build_run_history_payload`
    and `build_run_metadata_payload`, so a degraded run reports identical
    per-document failure detail (relative path, converter, exception class,
    sanitized reason) in both persisted artifacts."""
    return _bounded_list([asdict(item) for item in classification.failed])


def build_run_history_payload(
    *,
    run_id: str,
    mode: str,
    manifest_status: str,
    started_at: str,
    generated_at: str,
    exit_code: int,
    metrics: dict,
    classification: NormalizerClassificationResult,
) -> dict:
    return {
        "schema_version": CURATED_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "mode": mode,
        "manifest_status": manifest_status,
        "started_at": started_at,
        "generated_at": generated_at,
        "exit_code": exit_code,
        "metrics": metrics,
        "converted_new": _bounded_list(classification.converted_new),
        "converted_stale": _bounded_list(classification.converted_stale),
        "converted_stale_converter": _bounded_list(classification.converted_stale_converter),
        "deferred": _bounded_list(classification.deferred),
        "unsupported": _bounded_list(classification.unsupported),
        "orphaned": _bounded_list(classification.orphaned),
        "failed": build_failure_details(classification),
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
    classification: "NormalizerClassificationResult",
) -> dict:
    return {
        "schema_version": CURATED_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "previous_run_id": previous_run_id,
        "mode": mode,
        "manifest_status": manifest_status,
        "started_at": started_at,
        "generated_at": generated_at,
        "exit_code": exit_code,
        "metrics": metrics,
        "failed": build_failure_details(classification),
    }


def _validate_curated_manifest_content(content: str, *, expected_count: int) -> None:
    lines = content.splitlines() if content else []
    if len(lines) != expected_count:
        raise ValueError(
            f"curated manifest line count mismatch: expected {expected_count}, got {len(lines)}"
        )

    previous_key: str | None = None
    seen: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        record = json.loads(line)
        missing = REQUIRED_CURATED_FIELDS - record.keys()
        if missing:
            raise ValueError(f"line {line_number} missing fields: {sorted(missing)}")

        key = record["relative_path"]
        if key in seen:
            raise ValueError(f"duplicate relative_path in staged curated manifest: {key}")
        seen.add(key)

        if previous_key is not None and key < previous_key:
            raise ValueError("staged curated manifest is not sorted by relative_path")
        previous_key = key


def _validate_metrics_invariants(metrics: dict) -> None:
    if metrics["source_total"] != metrics["text_native"] + metrics["deferred"] + metrics["unsupported"]:
        raise ValueError(
            "metrics invariant violated: source_total != text_native + deferred + unsupported"
        )
    if metrics["text_native"] != (
        metrics["converted_new"]
        + metrics["converted_stale"]
        + metrics["converted_stale_converter"]
        + metrics["unchanged"]
        + metrics["failed"]
    ):
        raise ValueError(
            "metrics invariant violated: text_native != converted_new + converted_stale + "
            "converted_stale_converter + unchanged + failed"
        )


def _validate_run_metadata_content(content: str) -> None:
    data = json.loads(content)
    missing = REQUIRED_RUN_METADATA_FIELDS - data.keys()
    if missing:
        raise ValueError(f"run metadata missing fields: {sorted(missing)}")

    metrics = data["metrics"]
    missing_metrics = REQUIRED_METRICS_FIELDS - metrics.keys()
    if missing_metrics:
        raise ValueError(f"run metadata metrics missing fields: {sorted(missing_metrics)}")

    _validate_metrics_invariants(metrics)


def _validate_run_history_content(content: str) -> None:
    data = json.loads(content)
    missing = REQUIRED_RUN_HISTORY_FIELDS - data.keys()
    if missing:
        raise ValueError(f"run history missing fields: {sorted(missing)}")


def stage_and_publish_run(
    *,
    curated_metadata_dir: Path,
    document_entries: dict[str, CuratedDocumentMetadata],
    run_history_payload: dict,
    run_metadata_payload: dict,
    run_id: str,
) -> tuple[Path, Path, Path]:
    """Stage the three curated-run artifacts, validate all of them, and only
    then publish. Publish order matches Knowledge Compiler V1.1: run history
    first, curated manifest second, run metadata (latest-run pointer) last.
    See `knowledge_compiler.manifest.stage_and_publish_run` for the full
    rationale -- this mirrors it exactly for the curated layer.
    """
    curated_manifest_path = curated_metadata_dir / DOCUMENT_NORMALIZER_MANIFEST_FILENAME
    run_metadata_path = curated_metadata_dir / NORMALIZER_RUN_METADATA_FILENAME
    run_history_path = curated_metadata_dir / RUN_HISTORY_SUBDIR / f"run_{run_id}.json"

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
                curated_manifest_path,
                manifest_content,
                lambda content: _validate_curated_manifest_content(
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

    return curated_manifest_path, run_metadata_path, run_history_path
