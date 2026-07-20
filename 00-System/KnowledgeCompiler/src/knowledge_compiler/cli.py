from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import ConfigError, load_config
from .diff import classify
from .manifest import (
    DOCUMENT_MANIFEST_FILENAME,
    RUN_HISTORY_SUBDIR,
    RUN_METADATA_FILENAME,
    ManifestCorruptError,
    backup_corrupt_manifest,
    build_run_history_payload,
    build_run_metadata_payload,
    load_previous_manifest,
    stage_and_publish_run,
    unique_run_id,
)
from .scanner import scan_with_report

INDEXES_MANIFEST_SUBDIR = "Metadata"

EXIT_CLEAN = 0
EXIT_HARD_STOP = 1
EXIT_DEGRADED = 2


@dataclass(frozen=True)
class CompilerRunResult:
    exit_code: int
    metrics: dict
    document_manifest_path: Path | None = None
    run_metadata_path: Path | None = None
    run_history_path: Path | None = None
    message: str | None = None


def _read_previous_run_id(run_metadata_path: Path) -> str | None:
    if not run_metadata_path.is_file():
        return None
    try:
        data = json.loads(run_metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data.get("run_id")


def run(root: Path | None = None, *, dry_run: bool = False, force_full: bool = False) -> CompilerRunResult:
    config = load_config(root)

    ingestion_dir = config.folder_path("ingestion")
    indexes_dir = config.folder_path("indexes") / INDEXES_MANIFEST_SUBDIR
    document_manifest_path = indexes_dir / DOCUMENT_MANIFEST_FILENAME
    run_metadata_path = indexes_dir / RUN_METADATA_FILENAME
    runs_dir = indexes_dir / RUN_HISTORY_SUBDIR

    started_at = datetime.now(timezone.utc).isoformat()
    run_id = unique_run_id(runs_dir)
    previous_run_id = _read_previous_run_id(run_metadata_path)
    manifest_existed = document_manifest_path.is_file()

    try:
        loaded = load_previous_manifest(document_manifest_path, migration_timestamp=started_at)
        manifest_status = (
            "missing" if not manifest_existed else ("valid-legacy-v1" if loaded.is_legacy else "valid")
        )
        previous = loaded.entries
    except ManifestCorruptError as exc:
        if not force_full:
            return CompilerRunResult(
                exit_code=EXIT_HARD_STOP,
                metrics={},
                message=(
                    f"{exc}\n"
                    "Rerun with --full to back up the invalid manifest and recover "
                    "as a full run, or restore a valid manifest manually."
                ),
            )
        backup_corrupt_manifest(document_manifest_path, run_id)
        manifest_status = "recovered-from-corrupt"
        previous = {}

    report = scan_with_report(ingestion_dir)

    result = classify(
        report.eligible,
        previous,
        force_full=force_full,
        run_timestamp=started_at,
        scan_failures=report.failed,
    )

    eligible = len(report.eligible) + len(report.failed)
    excluded = len(report.excluded)
    discovered = eligible + excluded
    processed = len(result.new) + len(result.modified) + len(result.unchanged)
    failed = len(result.failed)

    finished_at = datetime.now(timezone.utc)
    duration_seconds = round(
        (finished_at - datetime.fromisoformat(started_at)).total_seconds(), 3
    )

    metrics = {
        "discovered": discovered,
        "eligible": eligible,
        "excluded": excluded,
        "processed": processed,
        "new": len(result.new),
        "modified": len(result.modified),
        "unchanged": len(result.unchanged),
        "deleted": len(result.deleted),
        "failed": failed,
        "hashes_recomputed": result.hashes_recomputed,
        "hashes_reused": result.hashes_reused,
        "duration_seconds": duration_seconds,
    }

    exit_code = EXIT_CLEAN if failed == 0 else EXIT_DEGRADED

    if dry_run:
        return CompilerRunResult(exit_code=exit_code, metrics=metrics)

    if force_full:
        mode = "full"
    elif manifest_status == "missing":
        mode = "full (no previous manifest)"
    elif manifest_status == "recovered-from-corrupt":
        mode = "full (recovered from corrupt manifest)"
    else:
        mode = "incremental"

    generated_at = finished_at.isoformat()

    run_history_payload = build_run_history_payload(
        run_id=run_id,
        mode=mode,
        manifest_status=manifest_status,
        started_at=started_at,
        generated_at=generated_at,
        exit_code=exit_code,
        metrics=metrics,
        classification=result,
        excluded=report.excluded,
    )
    run_metadata_payload = build_run_metadata_payload(
        run_id=run_id,
        previous_run_id=previous_run_id,
        mode=mode,
        manifest_status=manifest_status,
        started_at=started_at,
        generated_at=generated_at,
        exit_code=exit_code,
        metrics=metrics,
    )

    document_manifest_path, run_metadata_path, run_history_path = stage_and_publish_run(
        indexes_dir=indexes_dir,
        document_entries=result.manifest_entries,
        run_history_payload=run_history_payload,
        run_metadata_payload=run_metadata_payload,
        run_id=run_id,
    )

    return CompilerRunResult(
        exit_code=exit_code,
        metrics=metrics,
        document_manifest_path=document_manifest_path,
        run_metadata_path=run_metadata_path,
        run_history_path=run_history_path,
    )


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else list(argv)

    # `normalize` dispatches to the V1.2.0 normalizer CLI entirely; an
    # optional leading `scan` is stripped so it can be used symmetrically,
    # but is never required -- every argv shape the existing scan tests
    # pass in (e.g. ["--root", ..., "--dry-run"]) falls through unchanged
    # to the parser below, exactly as before this dispatch was added.
    if raw_argv and raw_argv[0] == "normalize":
        from .normalizer_cli import main as normalize_main

        return normalize_main(raw_argv[1:])
    if raw_argv and raw_argv[0] == "scan":
        raw_argv = raw_argv[1:]

    parser = argparse.ArgumentParser(
        prog="knowledge-compiler",
        description="Build a deterministic, incremental inventory manifest of the AI Hub ingestion layer.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Path inside the AI Hub repository (defaults to the current directory).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing any files (no manifest, no run metadata, no run history).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force hash recomputation for every eligible file. Also required to recover from a corrupt previous manifest.",
    )
    args = parser.parse_args(raw_argv)

    try:
        result = run(args.root, dry_run=args.dry_run, force_full=args.full)
    except (ConfigError, NotADirectoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_HARD_STOP

    if result.message:
        print(result.message, file=sys.stderr)

    m = result.metrics
    if m:
        print(f"discovered={m['discovered']} eligible={m['eligible']} excluded={m['excluded']}")
        print(
            f"processed={m['processed']} new={m['new']} modified={m['modified']} "
            f"unchanged={m['unchanged']} deleted={m['deleted']}"
        )
        print(
            f"failed={m['failed']} hashes_recomputed={m['hashes_recomputed']} "
            f"hashes_reused={m['hashes_reused']} duration_seconds={m['duration_seconds']}"
        )

    if args.dry_run:
        print("Dry run: no files were written.")
    elif result.document_manifest_path is not None:
        print(f"Document manifest written to {result.document_manifest_path}")
        print(f"Run metadata written to {result.run_metadata_path}")
        print(f"Run history written to {result.run_history_path}")

    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
