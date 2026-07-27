from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import converters
from .converters import DEFERRED_EXTENSIONS, SUPPORTED_EXTENSIONS, ConversionError, convert
from .curated_manifest import CuratedDocumentMetadata
from .document_type import document_type_for
from .io_utils import stage_text
from .language import language_for
from .metadata import DocumentMetadata


@dataclass(frozen=True)
class FailedConversion:
    relative_path: str
    converter_id: str
    reason: str
    error_type: str
    previous_entry_preserved: bool


@dataclass(frozen=True)
class NormalizerClassificationResult:
    curated_entries: dict[str, CuratedDocumentMetadata]
    converted_new: list[str] = field(default_factory=list)
    converted_stale: list[str] = field(default_factory=list)
    converted_stale_converter: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    failed: list[FailedConversion] = field(default_factory=list)
    orphaned: list[str] = field(default_factory=list)


def _output_sha256(canonical_markdown: str) -> str:
    return hashlib.sha256(canonical_markdown.encode("utf-8")).hexdigest()


def _sanitize_reason(exc: Exception, *, ingestion_dir: Path, relative_path: str) -> str:
    """Reduce an exception to a concise, path-sanitized reason string.

    Never includes document content (no exception raised here ever carries
    it). Absolute filesystem paths -- which `OSError` messages embed via
    `strerror: 'filename'` -- are collapsed to the document's own
    `relative_path` so the reason never leaks the local filesystem layout.
    """
    reason = str(exc)
    absolute_path = str(ingestion_dir / relative_path)
    reason = reason.replace(absolute_path, relative_path)
    ingestion_str = str(ingestion_dir)
    if ingestion_str:
        reason = reason.replace(ingestion_str + "/", "").replace(ingestion_str, "")
    return reason


def classify_normalization(
    source_entries: dict[str, DocumentMetadata],
    previous_curated: dict[str, CuratedDocumentMetadata],
    *,
    ingestion_dir: Path,
    markdown_dir: Path,
    run_timestamp: str,
    dry_run: bool,
) -> NormalizerClassificationResult:
    """Classify every document in the V1.1 source manifest against the
    previous curated manifest, converting text-native documents whose state
    requires it, and carrying forward everything else.

    Mutually exclusive per-document states: converted_new, converted_stale,
    converted_stale_converter, unchanged, unsupported, deferred, failed.
    `orphaned` is a separate dimension: previous curated entries whose
    source no longer appears in `source_entries` -- they are carried
    forward untouched (their output files are never rewritten or deleted).

    In `dry_run` mode, converters are still invoked (so conversion failures
    surface in the metrics) but nothing is written to disk -- not even a
    temporary artifact.
    """
    converted_new: list[str] = []
    converted_stale: list[str] = []
    converted_stale_converter: list[str] = []
    unchanged: list[str] = []
    unsupported: list[str] = []
    deferred: list[str] = []
    failed: list[FailedConversion] = []
    curated_entries: dict[str, CuratedDocumentMetadata] = {}
    seen_paths: set[str] = set()

    for relative_path in sorted(source_entries):
        source_entry = source_entries[relative_path]
        seen_paths.add(relative_path)
        extension = source_entry.extension
        prev = previous_curated.get(relative_path)

        if extension not in SUPPORTED_EXTENSIONS:
            if extension in DEFERRED_EXTENSIONS:
                deferred.append(relative_path)
            else:
                unsupported.append(relative_path)
            continue

        # Precedence when both conditions hold in the same run: a converter
        # upgrade is a structural, repository-wide reason to reconvert and
        # takes priority over a same-run source content change.
        if prev is None:
            state = "converted_new"
        elif (
            converters.CONVERTER_ID != prev.converter_id
            or converters.CONVERTER_VERSION != prev.converter_version
        ):
            state = "converted_stale_converter"
        elif prev.source_sha256 != source_entry.sha256:
            state = "converted_stale"
        else:
            state = "unchanged"

        if state == "unchanged":
            unchanged.append(relative_path)
            curated_entries[relative_path] = prev
            continue

        try:
            source_bytes = (ingestion_dir / relative_path).read_bytes()
            source_text = source_bytes.decode("utf-8")

            document_id = prev.document_id if prev is not None else str(uuid.uuid4())
            document_type = document_type_for(source_entry.knowledge_source)
            language = language_for(source_text)

            result = convert(
                extension=extension,
                source_text=source_text,
                relative_path=relative_path,
                source_sha256=source_entry.sha256,
                knowledge_source=source_entry.knowledge_source,
                document_id=document_id,
                document_type=document_type,
                language=language,
            )

            output_relative_path = f"{relative_path}.md"
            output_sha256 = _output_sha256(result.canonical_markdown)

            if not dry_run:
                output_path = markdown_dir / output_relative_path
                artifact = stage_text(output_path, result.canonical_markdown)
                artifact.publish()

            entry = CuratedDocumentMetadata(
                document_id=document_id,
                relative_path=relative_path,
                knowledge_source=source_entry.knowledge_source,
                document_type=document_type,
                language=language,
                source_extension=extension,
                source_sha256=source_entry.sha256,
                converter_id=converters.CONVERTER_ID,
                converter_version=converters.CONVERTER_VERSION,
                output_relative_path=output_relative_path,
                output_sha256=output_sha256,
                first_seen_at=prev.first_seen_at if prev is not None else run_timestamp,
                last_converted_at=run_timestamp,
            )
            curated_entries[relative_path] = entry

            if state == "converted_new":
                converted_new.append(relative_path)
            elif state == "converted_stale_converter":
                converted_stale_converter.append(relative_path)
            else:
                converted_stale.append(relative_path)

        except (ConversionError, OSError, UnicodeDecodeError) as exc:
            failed.append(
                FailedConversion(
                    relative_path=relative_path,
                    converter_id=converters.CONVERTER_ID,
                    reason=_sanitize_reason(
                        exc, ingestion_dir=ingestion_dir, relative_path=relative_path
                    ),
                    error_type=type(exc).__name__,
                    previous_entry_preserved=prev is not None,
                )
            )
            if prev is not None:
                curated_entries[relative_path] = prev

    orphaned: list[str] = []
    for relative_path in sorted(previous_curated):
        if relative_path not in seen_paths:
            orphaned.append(relative_path)
            curated_entries[relative_path] = previous_curated[relative_path]

    return NormalizerClassificationResult(
        curated_entries=curated_entries,
        converted_new=converted_new,
        converted_stale=converted_stale,
        converted_stale_converter=converted_stale_converter,
        unchanged=unchanged,
        unsupported=unsupported,
        deferred=deferred,
        failed=failed,
        orphaned=orphaned,
    )
