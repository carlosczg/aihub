from __future__ import annotations

import unittest

from knowledge_compiler.language import (
    LANGUAGE_ENGLISH,
    LANGUAGE_SPANISH,
    LANGUAGE_UNDETERMINED,
    SUPPORTED_LANGUAGES,
    language_for,
)


class LanguageForTests(unittest.TestCase):
    def test_spanish_content_is_detected(self) -> None:
        text = (
            "El documento describe la propuesta para el cliente y el "
            "equipo en la reunion de hoy."
        )
        self.assertEqual(language_for(text), LANGUAGE_SPANISH)

    def test_english_content_is_detected(self) -> None:
        text = (
            "The document describes the proposal for the client and the "
            "team in this meeting today."
        )
        self.assertEqual(language_for(text), LANGUAGE_ENGLISH)

    def test_too_few_words_is_undetermined(self) -> None:
        self.assertEqual(language_for("x = 1"), LANGUAGE_UNDETERMINED)
        self.assertEqual(language_for(""), LANGUAGE_UNDETERMINED)

    def test_enough_words_but_no_stopword_hits_is_undetermined(self) -> None:
        # Plenty of words, but none of them are Spanish/English function
        # words (e.g. an identifier-heavy code snippet or proper nouns).
        text = "Zeta Corp Omnigent Aihub Knowledge Compiler Curated Markdown Portfolio"
        self.assertEqual(language_for(text), LANGUAGE_UNDETERMINED)

    def test_near_tied_score_is_undetermined(self) -> None:
        # Roughly equal Spanish and English stopword hits -- below the
        # required winning margin, so the heuristic refuses to guess.
        text = "el la de en the a of to y and el la"
        self.assertEqual(language_for(text), LANGUAGE_UNDETERMINED)

    def test_supported_languages_are_exactly_es_en_und(self) -> None:
        self.assertEqual(SUPPORTED_LANGUAGES, frozenset({"es", "en", "und"}))


if __name__ == "__main__":
    unittest.main()
