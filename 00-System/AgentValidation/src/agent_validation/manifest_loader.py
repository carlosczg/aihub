from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

MANIFEST_FIELDS = (
    "converter_id",
    "converter_version",
    "document_id",
    "document_type",
    "first_seen_at",
    "knowledge_source",
    "language",
    "last_converted_at",
    "output_relative_path",
    "output_sha256",
    "relative_path",
    "source_extension",
    "source_sha256",
)


class ManifestError(RuntimeError):
    pass


@dataclass(frozen=True)
class ManifestEntry:
    converter_id: str
    converter_version: str
    document_id: str
    document_type: str
    first_seen_at: str
    knowledge_source: str
    language: str
    last_converted_at: str
    output_relative_path: str
    output_sha256: str
    relative_path: str
    source_extension: str
    source_sha256: str


def load_manifest(manifest_path: Path) -> list[ManifestEntry]:
    """Load the curated document-normalizer manifest (JSONL, one object per line).

    The manifest is the catalog of curated documents -- this function never
    rescans 02-Curated/Markdown itself, it only parses the manifest file at
    the given path.
    """
    if not manifest_path.is_file():
        raise ManifestError(f"Manifest not found at '{manifest_path}'")

    entries: list[ManifestEntry] = []
    text = manifest_path.read_text(encoding="utf-8")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ManifestError(
                f"Invalid JSON on line {line_number} of '{manifest_path}': {exc}"
            ) from exc

        if not isinstance(record, dict):
            raise ManifestError(f"Line {line_number} of '{manifest_path}' is not a JSON object")

        missing = [field for field in MANIFEST_FIELDS if field not in record]
        if missing:
            raise ManifestError(
                f"Line {line_number} of '{manifest_path}' missing fields: {sorted(missing)}"
            )

        entries.append(ManifestEntry(**{field: record[field] for field in MANIFEST_FIELDS}))

    return entries
