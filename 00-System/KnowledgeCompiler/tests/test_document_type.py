from __future__ import annotations

import unittest

from knowledge_compiler.document_type import DOCUMENT_TYPE_UNKNOWN, document_type_for


class DocumentTypeForTests(unittest.TestCase):
    def test_exact_adr_001_mapping(self) -> None:
        self.assertEqual(document_type_for("OneDrive-Proposals"), "proposal")
        self.assertEqual(document_type_for("OneDrive-Marketing"), "marketing")
        self.assertEqual(document_type_for("OneDrive-Portfolio"), "portfolio")

    def test_unmapped_knowledge_source_returns_unknown(self) -> None:
        self.assertEqual(document_type_for("Manual"), DOCUMENT_TYPE_UNKNOWN)
        self.assertEqual(document_type_for("SomeFutureCategory"), DOCUMENT_TYPE_UNKNOWN)
        self.assertEqual(document_type_for(""), DOCUMENT_TYPE_UNKNOWN)

    def test_mapping_is_case_sensitive_and_exact(self) -> None:
        # Not a classifier: no normalization, no fuzzy matching.
        self.assertEqual(document_type_for("onedrive-proposals"), DOCUMENT_TYPE_UNKNOWN)
        self.assertEqual(document_type_for("OneDrive-Proposals "), DOCUMENT_TYPE_UNKNOWN)


if __name__ == "__main__":
    unittest.main()
