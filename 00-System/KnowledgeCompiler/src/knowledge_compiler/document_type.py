from __future__ import annotations

DOCUMENT_TYPE_UNKNOWN = "unknown"

# Minimal 1:1 mapping from `knowledge_source` to `document_type`, per
# ADR-001. A lookup table, not a classifier: no heuristics, no customer/
# industry/service inference, no new branches without a separate future
# decision.
_DOCUMENT_TYPE_BY_KNOWLEDGE_SOURCE = {
    "OneDrive-Proposals": "proposal",
    "OneDrive-Marketing": "marketing",
    "OneDrive-Portfolio": "portfolio",
}


def document_type_for(knowledge_source: str) -> str:
    """Return the `document_type` for a given `knowledge_source`.

    Any `knowledge_source` outside the three mapped values -- including any
    future OneDrive sync category -- resolves to `DOCUMENT_TYPE_UNKNOWN`
    under this table's own "anything else" rule; no code change is needed
    when a new `knowledge_source` value appears.
    """
    return _DOCUMENT_TYPE_BY_KNOWLEDGE_SOURCE.get(knowledge_source, DOCUMENT_TYPE_UNKNOWN)
