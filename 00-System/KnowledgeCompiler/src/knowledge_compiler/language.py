from __future__ import annotations

import re

LANGUAGE_UNDETERMINED = "und"
LANGUAGE_SPANISH = "es"
LANGUAGE_ENGLISH = "en"

SUPPORTED_LANGUAGES = frozenset({LANGUAGE_SPANISH, LANGUAGE_ENGLISH, LANGUAGE_UNDETERMINED})

_WORD_PATTERN = re.compile(r"[a-zA-ZáéíóúñüÁÉÍÓÚÑÜ]+")

_MIN_WORD_COUNT = 8
_MIN_STOPWORD_SCORE = 2
_MIN_WINNING_MARGIN_RATIO = 1.5

# Short, high-frequency function words. Deliberately disjoint from
# `_ENGLISH_STOPWORDS` (aside from "no", which is a genuine function word in
# both languages) so a match only ever counts toward one language's score.
_SPANISH_STOPWORDS = frozenset(
    {
        "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del",
        "en", "y", "que", "es", "son", "para", "por", "con", "como", "su",
        "sus", "al", "lo", "le", "les", "se", "no", "mas", "más", "pero",
        "o", "u", "este", "esta", "estos", "estas", "ese", "esa", "esos",
        "esas", "muy", "también", "desde", "hasta", "sobre", "entre",
    }
)

_ENGLISH_STOPWORDS = frozenset(
    {
        "the", "is", "a", "an", "of", "to", "and", "in", "on", "for",
        "with", "that", "this", "are", "was", "were", "be", "been", "have",
        "has", "had", "it", "as", "at", "by", "from", "or", "but", "not",
        "you", "your", "we", "our", "they", "their", "he", "she", "his",
        "her", "its",
    }
)


def language_for(text: str) -> str:
    """Return a conservative `es` / `en` / `und` guess for `text`.

    Dependency-free stopword-frequency heuristic, not a classifier: too few
    words, too few stopword hits, or a near-tied score between the two
    languages all resolve to `und` rather than guessing -- a wrong `und` is
    cheaper than a wrong `es`/`en`.
    """
    words = [word.lower() for word in _WORD_PATTERN.findall(text)]
    if len(words) < _MIN_WORD_COUNT:
        return LANGUAGE_UNDETERMINED

    es_score = sum(1 for word in words if word in _SPANISH_STOPWORDS)
    en_score = sum(1 for word in words if word in _ENGLISH_STOPWORDS)

    if es_score < _MIN_STOPWORD_SCORE and en_score < _MIN_STOPWORD_SCORE:
        return LANGUAGE_UNDETERMINED

    if es_score > en_score * _MIN_WINNING_MARGIN_RATIO:
        return LANGUAGE_SPANISH
    if en_score > es_score * _MIN_WINNING_MARGIN_RATIO:
        return LANGUAGE_ENGLISH
    return LANGUAGE_UNDETERMINED
