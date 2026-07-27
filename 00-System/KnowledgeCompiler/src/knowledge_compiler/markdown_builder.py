from __future__ import annotations

import yaml

AIHUB_FRONT_MATTER_SCHEMA_VERSION = 1

_FRONT_MATTER_OPEN = "---"
_FRONT_MATTER_CLOSE = {"---", "..."}


def parse_source_front_matter(text: str) -> tuple[dict | None, str]:
    """Detect and parse a leading YAML front matter block in `text`.

    Returns `(source_metadata, body)`. `source_metadata` is the parsed
    front matter as a dict, or `None` if no valid front matter block was
    detected. `body` is everything after the closing delimiter line,
    preserved verbatim (original line endings untouched) -- or the entire
    original `text` verbatim when no front matter is detected.

    Detection requires the first line to be exactly `---` and a later line
    that is exactly `---` or `...` (both stripped of trailing `\\r`/`\\n`
    only, never rstripped of content). A block whose YAML fails to parse,
    or whose parsed value is not a mapping, is treated as "no front matter"
    so the original text is preserved untouched rather than silently
    dropped.
    """
    lines = text.splitlines(keepends=True)
    if not lines:
        return None, text

    if lines[0].rstrip("\r\n") != _FRONT_MATTER_OPEN:
        return None, text

    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n") not in _FRONT_MATTER_CLOSE:
            continue

        front_matter_text = "".join(lines[1:index])
        body = "".join(lines[index + 1 :])

        try:
            parsed = yaml.safe_load(front_matter_text)
        except yaml.YAMLError:
            return None, text

        if parsed is None:
            parsed = {}
        if not isinstance(parsed, dict):
            return None, text

        return parsed, body

    return None, text


def build_front_matter(
    *,
    document_id: str,
    relative_path: str,
    extension: str,
    source_sha256: str,
    knowledge_source: str,
    document_type: str,
    language: str,
    converter_id: str,
    converter_version: str,
    source_metadata: dict | None,
) -> dict:
    """Build the AI Hub front matter payload for a converted document.

    Deliberately excludes any timestamp or run identifier: canonical
    Markdown must be byte-identical for the same source bytes and converter
    version, regardless of when or in which run it was produced.

    `derived_metadata` is always `None` here -- per ADR-001, it is a
    reserved field for future deterministic, rule-based derivations only.
    No AI-generated or agent-generated content may populate it at this
    stage.
    """
    return {
        "schema_version": AIHUB_FRONT_MATTER_SCHEMA_VERSION,
        "document_id": document_id,
        "source_relative_path": relative_path,
        "source_extension": extension,
        "source_sha256": source_sha256,
        "knowledge_source": knowledge_source,
        "document_type": document_type,
        "language": language,
        "converter_id": converter_id,
        "converter_version": converter_version,
        "source_metadata": source_metadata,
        "derived_metadata": None,
    }


def render_canonical_markdown(*, front_matter: dict, body: str) -> str:
    """Render exactly one AI Hub YAML front matter block followed by `body`.

    `yaml.safe_dump` with `sort_keys=True` and a fixed `default_flow_style`
    makes the serialized front matter deterministic for a given payload.
    `body` is appended verbatim -- its content and line endings are never
    altered.
    """
    front_matter_text = yaml.safe_dump(
        front_matter,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
    )
    return f"---\n{front_matter_text}---\n{body}"


def fence_for(content: str) -> str:
    """Pick a backtick fence longer than any run of backticks in `content`,
    so the fenced block can never be broken by content that itself contains
    backtick runs (minimum length 3, matching standard Markdown fencing)."""
    max_run = 0
    current_run = 0
    for char in content:
        if char == "`":
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    return "`" * max(3, max_run + 1)


def wrap_fenced(content: str, language: str) -> str:
    """Wrap `content` verbatim in a fenced code block tagged with `language`.

    A trailing newline is appended only if `content` does not already end
    with one -- required for valid fence syntax, not a change to the
    content's own line endings.
    """
    fence = fence_for(content)
    if content and not content.endswith(("\n", "\r")):
        content = content + "\n"
    return f"{fence}{language}\n{content}{fence}\n"
