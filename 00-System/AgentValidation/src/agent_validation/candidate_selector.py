from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .manifest_loader import ManifestEntry

MAX_CANDIDATES = 8

METADATA_FIELDS = ("document_type", "knowledge_source", "language", "source_extension")

STOPWORDS = frozenset(
    {
        "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or", "is",
        "are", "was", "were", "be", "been", "being", "what", "which", "who",
        "whom", "how", "do", "does", "did", "this", "that", "these", "those",
        "with", "by", "from", "as", "it", "its", "any", "there", "their", "they",
        "we", "you", "your", "i", "he", "she", "them", "his", "her", "if", "but",
        "not", "no", "so", "such", "than", "then", "too", "very", "can", "could",
        "should", "would", "will", "shall", "may", "might", "about", "into",
        "over", "under", "up", "down", "out", "off", "again", "further", "once",
        "here", "when", "where", "why", "all", "each", "few", "more", "most",
        "other", "some", "own", "same", "just", "also",
    }
)

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split on non-alphanumeric runs, drop stopwords."""
    tokens = _TOKEN_PATTERN.findall(text.lower())
    return [token for token in tokens if len(token) > 1 and token not in STOPWORDS]


@dataclass(frozen=True)
class NoCandidatesFound:
    """Explicit sentinel distinguishing 'ranked but nothing scored' from an
    empty list, which would otherwise be ambiguous with an unranked call."""

    reason: str


@dataclass(frozen=True)
class RankedCandidate:
    entry: ManifestEntry
    score: int
    matched_tokens: tuple[str, ...]


def _mentions_value(question_lower: str, value: str) -> bool:
    value_lower = value.lower().strip()
    if not value_lower:
        return False
    # Extensions start with "." (a non-word char), so a leading \b would
    # spuriously fail whenever the extension is preceded by whitespace
    # (e.g. "the .py files") -- only the trailing boundary matters there.
    # Everything else gets full \b...\b so e.g. language code "es" cannot
    # match inside an unrelated word like "represent".
    if value_lower.startswith("."):
        pattern = re.escape(value_lower) + r"\b"
        return re.search(pattern, question_lower) is not None

    # document_type/knowledge_source values are singular ("proposal",
    # "portfolio") but questions naturally use plurals ("proposals",
    # "portfolio items"). A plain \bvalue\b match would silently drop an
    # entire knowledge_source/document_type from the pool whenever the
    # question pluralizes it -- so also accept the simple "+s" plural.
    # Deliberately not real stemming/NLP, just this one deterministic rule.
    words = [value_lower] if value_lower.endswith("s") else [value_lower, value_lower + "s"]
    pattern = r"\b(?:" + "|".join(re.escape(word) for word in words) + r")\b"
    return re.search(pattern, question_lower) is not None


def _apply_metadata_filters(question: str, entries: list[ManifestEntry]) -> list[ManifestEntry]:
    question_lower = question.lower()
    active_filters: dict[str, set[str]] = {}

    for field in METADATA_FIELDS:
        known_values = {getattr(entry, field) for entry in entries}
        mentioned = {value for value in known_values if _mentions_value(question_lower, value)}
        if mentioned:
            active_filters[field] = mentioned

    if not active_filters:
        return list(entries)

    return [
        entry
        for entry in entries
        if all(getattr(entry, field) in values for field, values in active_filters.items())
    ]


def select_candidates(
    question: str,
    entries: list[ManifestEntry],
    *,
    markdown_root: Path,
) -> list[RankedCandidate] | NoCandidatesFound:
    """Deterministic, explainable candidate selection. No embeddings, no
    vector math, no ML.

    1. Metadata filters narrow the pool to entries whose document_type,
       knowledge_source, language, or source_extension is literally
       mentioned in the question text (case-insensitive, word-bounded
       match against the manifest's own known values).
    2. Remaining entries are scored by keyword-token overlap between the
       question and (a) the entry's relative_path / output_relative_path
       and (b) the plain-text body of its curated Markdown file (read via
       output_relative_path, resolved against markdown_root).
    3. Ranked by score descending; ties broken by relative_path ascending
       -- a stable, deterministic secondary key, so repeated runs on
       identical input always produce identical output order.
    4. Capped to MAX_CANDIDATES.
    5. Zero scored entries returns the explicit NoCandidatesFound sentinel,
       distinct from an empty list.
    """
    question_tokens = set(tokenize(question))
    pool = _apply_metadata_filters(question, entries)

    scored: list[RankedCandidate] = []
    for entry in pool:
        path_tokens = set(tokenize(entry.relative_path)) | set(tokenize(entry.output_relative_path))

        markdown_path = markdown_root / entry.output_relative_path
        try:
            body_text = markdown_path.read_text(encoding="utf-8")
        except OSError:
            body_text = ""
        body_tokens = set(tokenize(body_text)) if body_text else set()

        matched = question_tokens & (path_tokens | body_tokens)
        if not matched:
            continue

        scored.append(
            RankedCandidate(entry=entry, score=len(matched), matched_tokens=tuple(sorted(matched)))
        )

    if not scored:
        return NoCandidatesFound(
            reason="No manifest entries matched the question after metadata filtering and keyword scoring."
        )

    scored.sort(key=lambda candidate: (-candidate.score, candidate.entry.relative_path))
    return scored[:MAX_CANDIDATES]
