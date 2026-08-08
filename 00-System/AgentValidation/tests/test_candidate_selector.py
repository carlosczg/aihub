from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_validation import candidate_selector
from agent_validation.candidate_selector import (
    MAX_CANDIDATES,
    NoCandidatesFound,
    RankedCandidate,
    select_candidates,
    tokenize,
)
from agent_validation.manifest_loader import ManifestEntry


def _entry(
    *,
    document_id: str,
    relative_path: str,
    document_type: str,
    knowledge_source: str,
    language: str,
    source_extension: str,
    output_relative_path: str,
) -> ManifestEntry:
    return ManifestEntry(
        converter_id="text_native",
        converter_version="1.1.0",
        document_id=document_id,
        document_type=document_type,
        first_seen_at="2026-07-20T03:09:09.550725+00:00",
        knowledge_source=knowledge_source,
        language=language,
        last_converted_at="2026-07-27T19:42:02.584090+00:00",
        output_relative_path=output_relative_path,
        output_sha256="c" * 64,
        relative_path=relative_path,
        source_extension=source_extension,
        source_sha256="d" * 64,
    )


FIXTURE_ENTRIES = [
    _entry(
        document_id="11111111-1111-1111-1111-111111111111",
        relative_path="OneDrive-Proposals/Caso_Financiera.py",
        document_type="proposal",
        knowledge_source="OneDrive-Proposals",
        language="es",
        source_extension=".py",
        output_relative_path="OneDrive-Proposals/Caso_Financiera.py.md",
    ),
    _entry(
        document_id="22222222-2222-2222-2222-222222222222",
        relative_path="OneDrive-Portfolio/DeployScript.sh",
        document_type="portfolio",
        knowledge_source="OneDrive-Portfolio",
        language="en",
        source_extension=".sh",
        output_relative_path="OneDrive-Portfolio/DeployScript.sh.md",
    ),
    _entry(
        document_id="33333333-3333-3333-3333-333333333333",
        relative_path="OneDrive-Marketing/BrandGuide.txt",
        document_type="marketing",
        knowledge_source="OneDrive-Marketing",
        language="en",
        source_extension=".txt",
        output_relative_path="OneDrive-Marketing/BrandGuide.txt.md",
    ),
    _entry(
        document_id="44444444-4444-4444-4444-444444444444",
        relative_path="OneDrive-Proposals/Unrelated.sql",
        document_type="proposal",
        knowledge_source="OneDrive-Proposals",
        language="und",
        source_extension=".sql",
        output_relative_path="OneDrive-Proposals/Unrelated.sql.md",
    ),
    _entry(
        document_id="55555555-5555-5555-5555-555555555555",
        relative_path="OneDrive-Portfolio/AnotherFinance.py",
        document_type="portfolio",
        knowledge_source="OneDrive-Portfolio",
        language="es",
        source_extension=".py",
        output_relative_path="OneDrive-Portfolio/AnotherFinance.py.md",
    ),
]

FIXTURE_BODIES = {
    "OneDrive-Proposals/Caso_Financiera.py.md": (
        "Este script realiza analisis financiero para el cliente. "
        "Contiene funciones de analytics."
    ),
    "OneDrive-Portfolio/DeployScript.sh.md": (
        "This deployment script automates a DevOps pipeline setup."
    ),
    "OneDrive-Marketing/BrandGuide.txt.md": (
        "Font licensing and brand typeface guidance for marketing materials."
    ),
    "OneDrive-Proposals/Unrelated.sql.md": (
        "Database schema definitions unrelated to finance."
    ),
    "OneDrive-Portfolio/AnotherFinance.py.md": (
        "Financial analytics dashboard script for portfolio review."
    ),
}


def _write_markdown_fixtures(root: Path) -> None:
    for relative, body in FIXTURE_BODIES.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")


class CandidateSelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.markdown_root = Path(self._tmp.name)
        _write_markdown_fixtures(self.markdown_root)
        self.addCleanup(self._tmp.cleanup)

    def test_metadata_filter_by_document_type(self) -> None:
        result = select_candidates(
            "What proposals exist?", FIXTURE_ENTRIES, markdown_root=self.markdown_root
        )

        self.assertIsInstance(result, list)
        self.assertTrue(all(c.entry.document_type == "proposal" for c in result))

    def test_metadata_filter_matches_plural_form_of_singular_value(self) -> None:
        # document_type is stored singular ("proposal") but questions
        # naturally pluralize it ("proposals"). Exercise the filter function
        # directly so this can't be masked by an unrelated keyword match.
        filtered = candidate_selector._apply_metadata_filters(
            "What proposals exist?", FIXTURE_ENTRIES
        )

        self.assertTrue(all(entry.document_type == "proposal" for entry in filtered))
        self.assertLess(len(filtered), len(FIXTURE_ENTRIES))
        self.assertEqual(
            {entry.document_id for entry in filtered},
            {"11111111-1111-1111-1111-111111111111", "44444444-4444-4444-4444-444444444444"},
        )

    def test_metadata_filter_by_knowledge_source(self) -> None:
        result = select_candidates(
            "What is stored under OneDrive-Marketing?",
            FIXTURE_ENTRIES,
            markdown_root=self.markdown_root,
        )

        self.assertIsInstance(result, list)
        self.assertTrue(all(c.entry.knowledge_source == "OneDrive-Marketing" for c in result))

    def test_metadata_filter_by_language(self) -> None:
        result = select_candidates(
            "Which financiera documents are written in es?",
            FIXTURE_ENTRIES,
            markdown_root=self.markdown_root,
        )

        self.assertIsInstance(result, list)
        self.assertTrue(all(c.entry.language == "es" for c in result))

    def test_metadata_filter_by_source_extension(self) -> None:
        result = select_candidates(
            "Show me .py files", FIXTURE_ENTRIES, markdown_root=self.markdown_root
        )

        self.assertIsInstance(result, list)
        self.assertTrue(all(c.entry.source_extension == ".py" for c in result))
        returned_ids = {c.entry.document_id for c in result}
        self.assertEqual(
            returned_ids,
            {"11111111-1111-1111-1111-111111111111", "55555555-5555-5555-5555-555555555555"},
        )

    def test_language_code_does_not_false_positive_on_substring(self) -> None:
        # "represent" contains the literal substring "es"; a naive substring
        # match (without word boundaries) would incorrectly trigger the
        # language=es filter and drop every English/und entry from the pool.
        filtered = candidate_selector._apply_metadata_filters(
            "What does it represent?", FIXTURE_ENTRIES
        )

        self.assertEqual(len(filtered), len(FIXTURE_ENTRIES))

    def test_keyword_ranking_matches_expected_file(self) -> None:
        result = select_candidates(
            "Financial analytics engagement", FIXTURE_ENTRIES, markdown_root=self.markdown_root
        )

        self.assertIsInstance(result, list)
        self.assertGreaterEqual(len(result), 1)
        top = result[0]
        self.assertEqual(top.entry.document_id, "55555555-5555-5555-5555-555555555555")
        self.assertIn("financial", top.matched_tokens)
        self.assertIn("analytics", top.matched_tokens)

    def test_results_capped_to_max_candidates(self) -> None:
        many_entries = []
        bodies = {}
        for i in range(MAX_CANDIDATES + 5):
            path = f"OneDrive-Portfolio/File{i}.txt"
            output_path = f"OneDrive-Portfolio/File{i}.txt.md"
            many_entries.append(
                _entry(
                    document_id=f"id-{i}",
                    relative_path=path,
                    document_type="portfolio",
                    knowledge_source="OneDrive-Portfolio",
                    language="en",
                    source_extension=".txt",
                    output_relative_path=output_path,
                )
            )
            bodies[output_path] = "keyword overlap test content"

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative, body in bodies.items():
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")

            result = select_candidates("keyword overlap test", many_entries, markdown_root=root)

        self.assertIsInstance(result, list)
        self.assertLessEqual(len(result), MAX_CANDIDATES)

    def test_ordering_is_deterministic_across_repeated_calls(self) -> None:
        first_run = select_candidates(
            "Financial analytics engagement", FIXTURE_ENTRIES, markdown_root=self.markdown_root
        )
        second_run = select_candidates(
            "Financial analytics engagement", FIXTURE_ENTRIES, markdown_root=self.markdown_root
        )

        self.assertIsInstance(first_run, list)
        self.assertIsInstance(second_run, list)
        first_order = [c.entry.document_id for c in first_run]
        second_order = [c.entry.document_id for c in second_run]
        self.assertEqual(first_order, second_order)

    def test_tie_break_is_relative_path_ascending(self) -> None:
        tied_entries = [
            _entry(
                document_id="zzz-id",
                relative_path="OneDrive-Portfolio/ZZZ.txt",
                document_type="portfolio",
                knowledge_source="OneDrive-Portfolio",
                language="en",
                source_extension=".txt",
                output_relative_path="OneDrive-Portfolio/ZZZ.txt.md",
            ),
            _entry(
                document_id="aaa-id",
                relative_path="OneDrive-Portfolio/AAA.txt",
                document_type="portfolio",
                knowledge_source="OneDrive-Portfolio",
                language="en",
                source_extension=".txt",
                output_relative_path="OneDrive-Portfolio/AAA.txt.md",
            ),
        ]

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for entry in tied_entries:
                target = root / entry.output_relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("shared keyword content", encoding="utf-8")

            result = select_candidates("shared keyword", tied_entries, markdown_root=root)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].score, result[1].score)
        self.assertEqual(
            [c.entry.relative_path for c in result],
            ["OneDrive-Portfolio/AAA.txt", "OneDrive-Portfolio/ZZZ.txt"],
        )

    def test_zero_candidates_returns_explicit_sentinel(self) -> None:
        result = select_candidates(
            "xyzabc123 nonexistent gibberish quokka",
            FIXTURE_ENTRIES,
            markdown_root=self.markdown_root,
        )

        self.assertIsInstance(result, NoCandidatesFound)
        self.assertNotIsInstance(result, list)

    def test_zero_candidates_is_distinguishable_from_empty_list(self) -> None:
        result = select_candidates(
            "xyzabc123 nonexistent gibberish quokka",
            FIXTURE_ENTRIES,
            markdown_root=self.markdown_root,
        )

        self.assertFalse(isinstance(result, list))
        with self.assertRaises(TypeError):
            len(result)  # NoCandidatesFound is not list-like on purpose

    def test_ranked_candidate_carries_all_citation_fields(self) -> None:
        result = select_candidates(
            "Financial analytics engagement", FIXTURE_ENTRIES, markdown_root=self.markdown_root
        )

        self.assertIsInstance(result, list)
        for candidate in result:
            self.assertIsInstance(candidate, RankedCandidate)
            entry = candidate.entry
            self.assertTrue(entry.document_id)
            self.assertTrue(entry.relative_path)
            self.assertTrue(entry.knowledge_source)
            self.assertTrue(entry.document_type)
            self.assertTrue(entry.language)
            self.assertTrue(entry.converter_version)
            self.assertTrue(entry.output_relative_path)
            self.assertEqual(len(entry.source_sha256), 64)
            short_sha = entry.source_sha256[:12]
            self.assertEqual(len(short_sha), 12)
            self.assertTrue(entry.source_sha256.startswith(short_sha))

    def test_tokenize_strips_punctuation_and_stopwords(self) -> None:
        tokens = tokenize("What is the Caso_Financiera.py file about?")

        self.assertEqual(tokens, ["caso", "financiera", "py", "file"])
        self.assertNotIn("the", tokens)
        self.assertNotIn("is", tokens)
        self.assertNotIn("what", tokens)


if __name__ == "__main__":
    unittest.main()
