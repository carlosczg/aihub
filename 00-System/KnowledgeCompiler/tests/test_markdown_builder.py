from __future__ import annotations

import unittest

from knowledge_compiler.markdown_builder import (
    build_front_matter,
    fence_for,
    parse_source_front_matter,
    render_canonical_markdown,
    wrap_fenced,
)


class ParseSourceFrontMatterTests(unittest.TestCase):
    def test_no_front_matter_returns_text_unchanged(self) -> None:
        text = "# Title\n\nbody text\n"
        metadata, body = parse_source_front_matter(text)
        self.assertIsNone(metadata)
        self.assertEqual(body, text)

    def test_empty_text_returns_none_and_empty_body(self) -> None:
        metadata, body = parse_source_front_matter("")
        self.assertIsNone(metadata)
        self.assertEqual(body, "")

    def test_valid_front_matter_is_parsed_and_body_preserved(self) -> None:
        text = "---\ntitle: Hello\ntags:\n  - a\n  - b\n---\nbody line 1\nbody line 2\n"
        metadata, body = parse_source_front_matter(text)
        self.assertEqual(metadata, {"title": "Hello", "tags": ["a", "b"]})
        self.assertEqual(body, "body line 1\nbody line 2\n")

    def test_front_matter_with_dot_dot_dot_closing_delimiter(self) -> None:
        text = "---\ntitle: X\n...\nbody\n"
        metadata, body = parse_source_front_matter(text)
        self.assertEqual(metadata, {"title": "X"})
        self.assertEqual(body, "body\n")

    def test_missing_closing_delimiter_yields_no_front_matter(self) -> None:
        text = "---\ntitle: X\nbody without closing fence\n"
        metadata, body = parse_source_front_matter(text)
        self.assertIsNone(metadata)
        self.assertEqual(body, text)

    def test_empty_front_matter_block_yields_empty_dict(self) -> None:
        text = "---\n---\nbody\n"
        metadata, body = parse_source_front_matter(text)
        self.assertEqual(metadata, {})
        self.assertEqual(body, "body\n")

    def test_non_mapping_front_matter_is_rejected(self) -> None:
        text = "---\n- a\n- b\n---\nbody\n"
        metadata, body = parse_source_front_matter(text)
        self.assertIsNone(metadata)
        self.assertEqual(body, text)

    def test_invalid_yaml_front_matter_is_rejected(self) -> None:
        text = "---\nkey: [unterminated\n---\nbody\n"
        metadata, body = parse_source_front_matter(text)
        self.assertIsNone(metadata)
        self.assertEqual(body, text)

    def test_crlf_line_endings_are_preserved_in_body(self) -> None:
        text = "---\r\ntitle: X\r\n---\r\nline one\r\nline two\r\n"
        metadata, body = parse_source_front_matter(text)
        self.assertEqual(metadata, {"title": "X"})
        self.assertEqual(body, "line one\r\nline two\r\n")

    def test_first_line_not_exactly_delimiter_yields_no_front_matter(self) -> None:
        text = "----\ntitle: X\n---\nbody\n"
        metadata, body = parse_source_front_matter(text)
        self.assertIsNone(metadata)
        self.assertEqual(body, text)


def _build_front_matter(**overrides) -> dict:
    kwargs = dict(
        document_id="00000000-0000-0000-0000-000000000000",
        relative_path="Manual/a.py",
        extension=".py",
        source_sha256="0" * 64,
        knowledge_source="Manual",
        document_type="unknown",
        language="und",
        converter_id="text_native",
        converter_version="1.0.0",
        source_metadata=None,
    )
    kwargs.update(overrides)
    return build_front_matter(**kwargs)


class BuildFrontMatterTests(unittest.TestCase):
    def test_contains_no_timestamp_or_run_id_keys(self) -> None:
        payload = _build_front_matter()
        forbidden_substrings = ("timestamp", "run_id", "generated_at", "converted_at")
        for key in payload:
            for forbidden in forbidden_substrings:
                self.assertNotIn(forbidden, key)

    def test_contains_the_full_closed_field_set(self) -> None:
        payload = _build_front_matter()
        expected_keys = {
            "schema_version",
            "document_id",
            "source_relative_path",
            "source_extension",
            "source_sha256",
            "knowledge_source",
            "document_type",
            "language",
            "converter_id",
            "converter_version",
            "source_metadata",
            "derived_metadata",
        }
        self.assertEqual(set(payload.keys()), expected_keys)

    def test_derived_metadata_is_always_none(self) -> None:
        payload = _build_front_matter()
        self.assertIsNone(payload["derived_metadata"])

    def test_document_id_document_type_and_language_are_passed_through(self) -> None:
        payload = _build_front_matter(
            document_id="11111111-1111-4111-8111-111111111111",
            document_type="proposal",
            language="es",
        )
        self.assertEqual(payload["document_id"], "11111111-1111-4111-8111-111111111111")
        self.assertEqual(payload["document_type"], "proposal")
        self.assertEqual(payload["language"], "es")


class RenderCanonicalMarkdownTests(unittest.TestCase):
    def test_produces_exactly_one_front_matter_block(self) -> None:
        front_matter = {"schema_version": 1, "source_relative_path": "a.txt"}
        rendered = render_canonical_markdown(front_matter=front_matter, body="hello\n")
        self.assertEqual(rendered.count("---\n"), 2)
        self.assertTrue(rendered.startswith("---\n"))
        self.assertTrue(rendered.endswith("hello\n"))

    def test_is_deterministic_for_same_inputs(self) -> None:
        front_matter = {"b": 2, "a": 1, "nested": {"z": 1, "y": 2}}
        first = render_canonical_markdown(front_matter=front_matter, body="body\n")
        second = render_canonical_markdown(front_matter=dict(front_matter), body="body\n")
        self.assertEqual(first, second)

    def test_preserves_body_line_endings_verbatim(self) -> None:
        body = "line1\r\nline2\r\n"
        rendered = render_canonical_markdown(front_matter={"a": 1}, body=body)
        self.assertTrue(rendered.endswith(body))


class FenceForTests(unittest.TestCase):
    def test_default_fence_is_three_backticks(self) -> None:
        self.assertEqual(fence_for("no backticks here"), "```")

    def test_fence_extends_beyond_longest_backtick_run(self) -> None:
        content = "some ```` text with four backticks"
        fence = fence_for(content)
        self.assertEqual(fence, "`" * 5)
        self.assertNotIn(fence, content)


class WrapFencedTests(unittest.TestCase):
    def test_wraps_content_with_language_tag(self) -> None:
        wrapped = wrap_fenced("print('hi')\n", "python")
        self.assertEqual(wrapped, "```python\nprint('hi')\n```\n")

    def test_adds_trailing_newline_before_closing_fence_if_missing(self) -> None:
        wrapped = wrap_fenced("no trailing newline", "text")
        self.assertEqual(wrapped, "```text\nno trailing newline\n```\n")

    def test_empty_content_still_produces_valid_fence(self) -> None:
        wrapped = wrap_fenced("", "text")
        self.assertEqual(wrapped, "```text\n```\n")


if __name__ == "__main__":
    unittest.main()
