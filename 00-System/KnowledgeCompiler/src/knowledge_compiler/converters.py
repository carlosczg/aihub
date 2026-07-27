from __future__ import annotations

from dataclasses import dataclass

from .markdown_builder import (
    build_front_matter,
    parse_source_front_matter,
    render_canonical_markdown,
    wrap_fenced,
)

CONVERTER_ID = "text_native"
CONVERTER_VERSION = "1.1.0"

# Extension -> fenced-code-block language tag. `.md` is handled separately
# (front-matter-aware passthrough, never fenced). `.csv` and `.xml` are
# deliberately absent: both are structured-data formats, not free text, and
# are deferred to a future Structured Data Compiler rather than treated as
# text-native (see DEFERRED_EXTENSIONS below).
_FENCED_LANGUAGE_BY_EXTENSION = {
    ".txt": "text",
    ".json": "json",
    ".yaml": "yaml",
    ".sql": "sql",
    ".py": "python",
    ".sh": "bash",
    ".java": "java",
}

SUPPORTED_EXTENSIONS = frozenset({".md", *_FENCED_LANGUAGE_BY_EXTENSION})

# Known, roadmapped-but-not-yet-implemented document families (PDF, legacy
# and modern Office, images/OCR, email, notebooks, diagrams, structured
# data). Distinct from "unsupported": deferred means AI Hub recognizes the
# type and intends to convert it in a future Knowledge Compiler version.
DEFERRED_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".rtf",
        ".odt",
        ".ods",
        ".odp",
        ".html",
        ".htm",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".tiff",
        ".tif",
        ".svg",
        ".eml",
        ".msg",
        ".ipynb",
        ".vsd",
        ".vsdx",
        # Structured data -- deferred to a future Structured Data Compiler
        # rather than treated as text-native.
        ".csv",
        ".xml",
    }
)


class ConversionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConversionResult:
    canonical_markdown: str
    source_metadata: dict | None


def convert(
    *,
    extension: str,
    source_text: str,
    relative_path: str,
    source_sha256: str,
    knowledge_source: str,
    document_id: str,
    document_type: str,
    language: str,
) -> ConversionResult:
    """Convert `source_text` (already decoded) into canonical Markdown.

    Deterministic for a given `(source_text, relative_path, source_sha256,
    knowledge_source, document_id, document_type, language)` tuple and the
    current `CONVERTER_VERSION`: no timestamps or run identifiers are
    introduced anywhere in the output.
    """
    if extension == ".md":
        source_metadata, body = parse_source_front_matter(source_text)
    elif extension in _FENCED_LANGUAGE_BY_EXTENSION:
        source_metadata = None
        body = wrap_fenced(source_text, _FENCED_LANGUAGE_BY_EXTENSION[extension])
    else:
        raise ConversionError(
            f"no text-native converter registered for extension '{extension}'"
        )

    front_matter = build_front_matter(
        document_id=document_id,
        relative_path=relative_path,
        extension=extension,
        source_sha256=source_sha256,
        knowledge_source=knowledge_source,
        document_type=document_type,
        language=language,
        converter_id=CONVERTER_ID,
        converter_version=CONVERTER_VERSION,
        source_metadata=source_metadata,
    )
    canonical_markdown = render_canonical_markdown(front_matter=front_matter, body=body)
    return ConversionResult(canonical_markdown=canonical_markdown, source_metadata=source_metadata)
