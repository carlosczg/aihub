from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import ConfigError, load_config
from .curated_manifest import (
    DOCUMENT_NORMALIZER_MANIFEST_FILENAME,
    NORMALIZER_RUN_METADATA_FILENAME,
    RUN_HISTORY_SUBDIR,
    CuratedManifestCorruptError,
    build_run_history_payload,
    build_run_metadata_payload,
    load_previous_curated_manifest,
    stage_and_publish_run,
    unique_run_id,
)
from .manifest import DOCUMENT_MANIFEST_FILENAME, ManifestCorruptError, load_previous_manifest
from .normalizer_diff import classify_normalization

INDEXES_MANIFEST_SUBDIR = "Metadata"
CURATED_METADATA_SUBDIR = "Metadata"
CURATED_MARKDOWN_SUBDIR = "Markdown"

# Duplicated (not imported) from `cli.py` deliberately: `cli.py` dispatches
# into this module for the `normalize` subcommand, so importing back from
# `cli.py` here would create a circular import for three plain integers.
EXIT_CLEAN = 0
EXIT_HARD_STOP = 1
EXIT_DEGRADED = 2


class SourceManifestMissingError(RuntimeError):
    pass


@dataclass(frozen=True)
class NormalizerRunResult:
    exit_code: int
    metrics: dict
    curated_manifest_path: Path | None = None
    run_metadata_path: Path | None = None
    run_history_path: Path | None = None
    message: str | None = None
    failures: list[dict] = field(default_factory=list)


def _read_previous_run_id(run_metadata_path: Path) -> str | None:
    if not run_metadata_path.is_file():
        return None
    try:
        data = json.loads(run_metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data.get("run_id")


def run(root: Path | None = None, *, dry_run: bool = False) -> NormalizerRunResult:
    """Consume the V1.1 document manifest as the source inventory (never
    rescans `01-Ingestion`) and produce the V1.2.0 curated manifest of
    canonical Markdown for text-native documents.
    """
    config = load_config(root)

    ingestion_dir = config.folder_path("ingestion")
    source_manifest_path = (
        config.folder_path("indexes") / INDEXES_MANIFEST_SUBDIR / DOCUMENT_MANIFEST_FILENAME
    )
    curated_dir = config.folder_path("curated")
    markdown_dir = curated_dir / CURATED_MARKDOWN_SUBDIR
    curated_metadata_dir = curated_dir / CURATED_METADATA_SUBDIR
    curated_manifest_path = curated_metadata_dir / DOCUMENT_NORMALIZER_MANIFEST_FILENAME
    run_metadata_path = curated_metadata_dir / NORMALIZER_RUN_METADATA_FILENAME
    runs_dir = curated_metadata_dir / RUN_HISTORY_SUBDIR

    if not source_manifest_path.is_file():
        raise SourceManifestMissingError(
            f"Knowledge Compiler V1.1 source manifest not found at '{source_manifest_path}'. "
            "Run `knowledge-compiler` (the scan step) before `knowledge-compiler normalize`."
        )

    started_at = datetime.now(timezone.utc).isoformat()
    run_id = unique_run_id(runs_dir)
    previous_run_id = _read_previous_run_id(run_metadata_path)

    loaded_source = load_previous_manifest(source_manifest_path, migration_timestamp=started_at)
    source_entries = loaded_source.entries

    curated_manifest_existed = curated_manifest_path.is_file()
    previous_curated = load_previous_curated_manifest(curated_manifest_path)
    manifest_status = "valid" if curated_manifest_existed else "missing"

    classification = classify_normalization(
        source_entries,
        previous_curated,
        ingestion_dir=ingestion_dir,
        markdown_dir=markdown_dir,
        run_timestamp=started_at,
        dry_run=dry_run,
    )

    failures = [asdict(item) for item in classification.failed]
    failed = len(classification.failed)
    text_native = (
        len(classification.converted_new)
        + len(classification.converted_stale)
        + len(classification.converted_stale_converter)
        + len(classification.unchanged)
        + failed
    )

    finished_at = datetime.now(timezone.utc)
    duration_seconds = round(
        (finished_at - datetime.fromisoformat(started_at)).total_seconds(), 3
    )

    metrics = {
        "source_total": len(source_entries),
        "text_native": text_native,
        "deferred": len(classification.deferred),
        "unsupported": len(classification.unsupported),
        "converted_new": len(classification.converted_new),
        "converted_stale": len(classification.converted_stale),
        "converted_stale_converter": len(classification.converted_stale_converter),
        "unchanged": len(classification.unchanged),
        "failed": failed,
        "orphaned": len(classification.orphaned),
        "duration_seconds": duration_seconds,
    }

    exit_code = EXIT_CLEAN if failed == 0 else EXIT_DEGRADED

    if dry_run:
        return NormalizerRunResult(exit_code=exit_code, metrics=metrics, failures=failures)

    mode = "initial" if manifest_status == "missing" else "incremental"
    generated_at = finished_at.isoformat()

    run_history_payload = build_run_history_payload(
        run_id=run_id,
        mode=mode,
        manifest_status=manifest_status,
        started_at=started_at,
        generated_at=generated_at,
        exit_code=exit_code,
        metrics=metrics,
        classification=classification,
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
        classification=classification,
    )

    curated_manifest_path, run_metadata_path, run_history_path = stage_and_publish_run(
        curated_metadata_dir=curated_metadata_dir,
        document_entries=classification.curated_entries,
        run_history_payload=run_history_payload,
        run_metadata_payload=run_metadata_payload,
        run_id=run_id,
    )

    return NormalizerRunResult(
        exit_code=exit_code,
        metrics=metrics,
        curated_manifest_path=curated_manifest_path,
        run_metadata_path=run_metadata_path,
        run_history_path=run_history_path,
        failures=failures,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="knowledge-compiler normalize",
        description=(
            "Convert text-native documents from the V1.1 document manifest into "
            "deterministic, traceable curated Markdown (Knowledge Compiler V1.2.0)."
        ),
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
        help=(
            "Report what would change without writing any files -- including "
            "temporary artifacts. Converters may still be invoked in-memory."
        ),
    )
    args = parser.parse_args(argv)

    try:
        result = run(args.root, dry_run=args.dry_run)
    except (
        ConfigError,
        NotADirectoryError,
        SourceManifestMissingError,
        ManifestCorruptError,
        CuratedManifestCorruptError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_HARD_STOP

    if result.message:
        print(result.message, file=sys.stderr)

    m = result.metrics
    if m:
        print(
            f"source_total={m['source_total']} text_native={m['text_native']} "
            f"deferred={m['deferred']} unsupported={m['unsupported']}"
        )
        print(
            f"converted_new={m['converted_new']} converted_stale={m['converted_stale']} "
            f"converted_stale_converter={m['converted_stale_converter']} unchanged={m['unchanged']}"
        )
        print(
            f"failed={m['failed']} orphaned={m['orphaned']} "
            f"duration_seconds={m['duration_seconds']}"
        )

    if result.failures:
        print("Failures:")
        for failure in result.failures:
            print(
                f"  - {failure['relative_path']} "
                f"[{failure['converter_id']}] "
                f"{failure['error_type']}: {failure['reason']}"
            )

    if args.dry_run:
        print("Dry run: no files were written.")
    elif result.curated_manifest_path is not None:
        print(f"Curated manifest written to {result.curated_manifest_path}")
        print(f"Run metadata written to {result.run_metadata_path}")
        print(f"Run history written to {result.run_history_path}")

    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
