from __future__ import annotations

import unittest

from knowledge_compiler.converters import (
    CONVERTER_ID,
    CONVERTER_VERSION,
    DEFERRED_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    ConversionError,
    convert,
)

_COMMON_KWARGS = dict(
    relative_path="Manual/example",
    source_sha256="0" * 64,
    knowledge_source="Manual",
)


class SupportedExtensionsTests(unittest.TestCase):
    def test_all_required_text_native_extensions_are_registered(self) -> None:
        required = {".md", ".txt", ".json", ".yaml", ".sql", ".py", ".sh", ".java"}
        self.assertEqual(SUPPORTED_EXTENSIONS, required)

    def test_csv_and_xml_are_not_registered_as_text_native(self) -> None:
        self.assertNotIn(".csv", SUPPORTED_EXTENSIONS)
        self.assertNotIn(".xml", SUPPORTED_EXTENSIONS)

    def test_deferred_and_supported_extensions_never_overlap(self) -> None:
        self.assertEqual(SUPPORTED_EXTENSIONS & DEFERRED_EXTENSIONS, set())

    def test_deferred_covers_office_pdf_and_multimodal_families(self) -> None:
        for ext in (".pdf", ".docx", ".doc", ".xlsx", ".pptx", ".png", ".ipynb", ".eml"):
            self.assertIn(ext, DEFERRED_EXTENSIONS)

    def test_deferred_covers_structured_data_families(self) -> None:
        # .csv and .xml are deferred to a future Structured Data Compiler
        # rather than treated as text-native, per V1.2.0 scope update.
        self.assertIn(".csv", DEFERRED_EXTENSIONS)
        self.assertIn(".xml", DEFERRED_EXTENSIONS)


class ConvertMarkdownTests(unittest.TestCase):
    def test_markdown_without_front_matter_is_passthrough_body(self) -> None:
        source_text = "# Title\n\nSome body text.\n"
        result = convert(extension=".md", source_text=source_text, **_COMMON_KWARGS)
        self.assertIsNone(result.source_metadata)
        self.assertTrue(result.canonical_markdown.endswith(source_text))
        self.assertEqual(result.canonical_markdown.count("source_metadata"), 1)

    def test_markdown_with_front_matter_preserves_it_under_source_metadata(self) -> None:
        source_text = "---\ntitle: My Doc\nauthor: Carlos\n---\n# Body\ncontent\n"
        result = convert(extension=".md", source_text=source_text, **_COMMON_KWARGS)
        self.assertEqual(result.source_metadata, {"title": "My Doc", "author": "Carlos"})
        self.assertTrue(result.canonical_markdown.endswith("# Body\ncontent\n"))
        self.assertIn("source_metadata:", result.canonical_markdown)
        self.assertIn("title: My Doc", result.canonical_markdown)

    def test_markdown_body_and_line_endings_preserved_after_front_matter(self) -> None:
        source_text = "---\ntitle: X\n---\r\nline1\r\nline2\r\n"
        result = convert(extension=".md", source_text=source_text, **_COMMON_KWARGS)
        self.assertTrue(result.canonical_markdown.endswith("line1\r\nline2\r\n"))


class ConvertFencedTextNativeTests(unittest.TestCase):
    def test_each_non_markdown_extension_produces_a_fenced_block(self) -> None:
        samples = {
            ".txt": "plain text\n",
            ".json": '{"a": 1}\n',
            ".yaml": "a: 1\n",
            ".sql": "SELECT 1;\n",
            ".py": "print('hi')\n",
            ".sh": "echo hi\n",
            ".java": "class A {}\n",
        }
        for extension, content in samples.items():
            with self.subTest(extension=extension):
                result = convert(extension=extension, source_text=content, **_COMMON_KWARGS)
                self.assertIsNone(result.source_metadata)
                self.assertIn("```", result.canonical_markdown)
                self.assertTrue(result.canonical_markdown.rstrip("\n").endswith("```"))
                self.assertIn(content.rstrip("\n"), result.canonical_markdown)

    def test_content_with_backtick_fences_does_not_break_the_wrapper(self) -> None:
        content = "some code\n```\nnested fence\n```\nmore\n"
        result = convert(extension=".sh", source_text=content, **_COMMON_KWARGS)
        # The wrapper fence must be longer than any backtick run in content.
        self.assertIn("````bash", result.canonical_markdown)


class ConvertUnsupportedTests(unittest.TestCase):
    def test_unsupported_extension_raises_conversion_error(self) -> None:
        with self.assertRaises(ConversionError):
            convert(extension=".pdf", source_text="whatever", **_COMMON_KWARGS)

    def test_csv_extension_is_no_longer_routed_as_text_native(self) -> None:
        with self.assertRaises(ConversionError):
            convert(extension=".csv", source_text="a,b,c\n1,2,3\n", **_COMMON_KWARGS)

    def test_xml_extension_is_no_longer_routed_as_text_native(self) -> None:
        with self.assertRaises(ConversionError):
            convert(extension=".xml", source_text="<root/>\n", **_COMMON_KWARGS)


class DeterminismTests(unittest.TestCase):
    def test_same_inputs_produce_byte_identical_output(self) -> None:
        content = "import os\nprint(os.getcwd())\n"
        first = convert(extension=".py", source_text=content, **_COMMON_KWARGS)
        second = convert(extension=".py", source_text=content, **_COMMON_KWARGS)
        self.assertEqual(first.canonical_markdown, second.canonical_markdown)

    def test_output_records_current_converter_identity(self) -> None:
        result = convert(extension=".txt", source_text="hi\n", **_COMMON_KWARGS)
        self.assertIn(f"converter_id: {CONVERTER_ID}", result.canonical_markdown)
        self.assertIn(f"converter_version: {CONVERTER_VERSION}", result.canonical_markdown)


if __name__ == "__main__":
    unittest.main()
