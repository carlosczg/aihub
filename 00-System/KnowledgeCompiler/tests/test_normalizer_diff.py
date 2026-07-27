from __future__ import annotations

import hashlib
import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from knowledge_compiler.converters import CONVERTER_ID, CONVERTER_VERSION
from knowledge_compiler.curated_manifest import CuratedDocumentMetadata
from knowledge_compiler.metadata import DocumentMetadata
from knowledge_compiler.normalizer_diff import classify_normalization

RUN_TS = "2026-07-19T00:00:00+00:00"


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _source_entry(relative_path: str, *, sha256: str, knowledge_source: str = "Manual") -> DocumentMetadata:
    return DocumentMetadata(
        relative_path=relative_path,
        file_name=Path(relative_path).name,
        extension=Path(relative_path).suffix.lower(),
        size_bytes=1,
        modified_at=RUN_TS,
        knowledge_source=knowledge_source,
        sha256=sha256,
        mime_type="text/plain",
        first_seen_at=RUN_TS,
        last_verified_at=RUN_TS,
    )


def _curated_entry(
    relative_path: str,
    *,
    source_sha256: str,
    converter_id: str = CONVERTER_ID,
    converter_version: str = CONVERTER_VERSION,
    document_id: str = "00000000-0000-0000-0000-000000000000",
    knowledge_source: str = "Manual",
    document_type: str = "unknown",
    language: str = "und",
) -> CuratedDocumentMetadata:
    return CuratedDocumentMetadata(
        document_id=document_id,
        relative_path=relative_path,
        knowledge_source=knowledge_source,
        document_type=document_type,
        language=language,
        source_extension=Path(relative_path).suffix.lower(),
        source_sha256=source_sha256,
        converter_id=converter_id,
        converter_version=converter_version,
        output_relative_path=f"{relative_path}.md",
        output_sha256="f" * 64,
        first_seen_at=RUN_TS,
        last_converted_at=RUN_TS,
    )


class ClassifyNormalizationTests(unittest.TestCase):
    def test_new_text_native_document_is_converted_and_written(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            content = b"print('hello')\n"
            (ingestion_dir / "Manual" / "a.py").write_bytes(content)

            source_entries = {"Manual/a.py": _source_entry("Manual/a.py", sha256=_hash(content))}

            result = classify_normalization(
                source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.converted_new, ["Manual/a.py"])
            self.assertEqual(result.failed, [])
            output_path = markdown_dir / "Manual" / "a.py.md"
            self.assertTrue(output_path.is_file())
            self.assertIn("Manual/a.py", result.curated_entries)

    def test_unchanged_document_is_carried_forward_without_reconversion(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            content = b"hello\n"
            (ingestion_dir / "Manual" / "a.txt").write_bytes(content)
            sha = _hash(content)

            source_entries = {"Manual/a.txt": _source_entry("Manual/a.txt", sha256=sha)}
            previous = {"Manual/a.txt": _curated_entry("Manual/a.txt", source_sha256=sha)}

            result = classify_normalization(
                source_entries, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.unchanged, ["Manual/a.txt"])
            self.assertEqual(result.converted_new, [])
            self.assertEqual(result.converted_stale, [])
            self.assertFalse((markdown_dir / "Manual" / "a.txt.md").exists())
            self.assertEqual(result.curated_entries["Manual/a.txt"], previous["Manual/a.txt"])

    def test_changed_source_hash_yields_converted_stale(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            new_content = b"new content\n"
            (ingestion_dir / "Manual" / "a.txt").write_bytes(new_content)

            source_entries = {
                "Manual/a.txt": _source_entry("Manual/a.txt", sha256=_hash(new_content))
            }
            previous = {"Manual/a.txt": _curated_entry("Manual/a.txt", source_sha256=_hash(b"old content\n"))}

            result = classify_normalization(
                source_entries, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.converted_stale, ["Manual/a.txt"])
            self.assertTrue((markdown_dir / "Manual" / "a.txt.md").is_file())

    def test_converter_version_mismatch_yields_converted_stale_converter(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            content = b"same content\n"
            (ingestion_dir / "Manual" / "a.txt").write_bytes(content)
            sha = _hash(content)

            source_entries = {"Manual/a.txt": _source_entry("Manual/a.txt", sha256=sha)}
            previous = {
                "Manual/a.txt": _curated_entry(
                    "Manual/a.txt", source_sha256=sha, converter_version="0.0.1-old"
                )
            }

            result = classify_normalization(
                source_entries, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.converted_stale_converter, ["Manual/a.txt"])
            self.assertEqual(result.curated_entries["Manual/a.txt"].converter_version, CONVERTER_VERSION)

    def test_deferred_extension_is_classified_deferred_with_no_curated_entry(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "OneDrive-Proposals").mkdir(parents=True)
            (ingestion_dir / "OneDrive-Proposals" / "doc.pdf").write_bytes(b"%PDF-1.4")

            source_entries = {
                "OneDrive-Proposals/doc.pdf": _source_entry(
                    "OneDrive-Proposals/doc.pdf", sha256=_hash(b"%PDF-1.4"), knowledge_source="OneDrive-Proposals"
                )
            }

            result = classify_normalization(
                source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.deferred, ["OneDrive-Proposals/doc.pdf"])
            self.assertNotIn("OneDrive-Proposals/doc.pdf", result.curated_entries)

    def test_csv_and_xml_are_classified_deferred_not_unsupported(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            (ingestion_dir / "Manual" / "data.csv").write_bytes(b"a,b\n1,2\n")
            (ingestion_dir / "Manual" / "data.xml").write_bytes(b"<root/>\n")

            source_entries = {
                "Manual/data.csv": _source_entry("Manual/data.csv", sha256=_hash(b"a,b\n1,2\n")),
                "Manual/data.xml": _source_entry("Manual/data.xml", sha256=_hash(b"<root/>\n")),
            }

            result = classify_normalization(
                source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(sorted(result.deferred), ["Manual/data.csv", "Manual/data.xml"])
            self.assertEqual(result.unsupported, [])
            self.assertNotIn("Manual/data.csv", result.curated_entries)
            self.assertNotIn("Manual/data.xml", result.curated_entries)

    def test_unknown_extension_is_classified_unsupported(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            (ingestion_dir / "Manual" / "a.bin").write_bytes(b"\x00\x01")

            source_entries = {
                "Manual/a.bin": _source_entry("Manual/a.bin", sha256=_hash(b"\x00\x01"))
            }

            result = classify_normalization(
                source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.unsupported, ["Manual/a.bin"])
            self.assertNotIn("Manual/a.bin", result.curated_entries)

    def test_undecodable_bytes_yield_failed_and_preserve_previous_entry(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            bad_bytes = b"\xff\xfe\x00broken"
            (ingestion_dir / "Manual" / "a.txt").write_bytes(bad_bytes)

            source_entries = {
                "Manual/a.txt": _source_entry("Manual/a.txt", sha256=_hash(bad_bytes))
            }
            previous = {"Manual/a.txt": _curated_entry("Manual/a.txt", source_sha256=_hash(b"old"))}

            result = classify_normalization(
                source_entries, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(len(result.failed), 1)
            self.assertEqual(result.failed[0].relative_path, "Manual/a.txt")
            self.assertTrue(result.failed[0].previous_entry_preserved)
            self.assertEqual(result.curated_entries["Manual/a.txt"], previous["Manual/a.txt"])

    def test_failed_document_without_previous_entry_gets_no_curated_entry(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            bad_bytes = b"\xff\xfe\x00broken"
            (ingestion_dir / "Manual" / "a.txt").write_bytes(bad_bytes)

            source_entries = {
                "Manual/a.txt": _source_entry("Manual/a.txt", sha256=_hash(bad_bytes))
            }

            result = classify_normalization(
                source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(len(result.failed), 1)
            self.assertFalse(result.failed[0].previous_entry_preserved)
            self.assertNotIn("Manual/a.txt", result.curated_entries)

    def test_orphaned_previous_entry_is_carried_forward_untouched(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            ingestion_dir.mkdir(parents=True)

            previous = {"Manual/gone.txt": _curated_entry("Manual/gone.txt", source_sha256=_hash(b"x"))}

            result = classify_normalization(
                {}, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.orphaned, ["Manual/gone.txt"])
            self.assertEqual(result.curated_entries["Manual/gone.txt"], previous["Manual/gone.txt"])
            self.assertFalse(markdown_dir.exists())

    def test_dry_run_writes_no_markdown_file(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            content = b"print(1)\n"
            (ingestion_dir / "Manual" / "a.py").write_bytes(content)

            source_entries = {"Manual/a.py": _source_entry("Manual/a.py", sha256=_hash(content))}

            result = classify_normalization(
                source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=True,
            )

            self.assertEqual(result.converted_new, ["Manual/a.py"])
            self.assertFalse(markdown_dir.exists())

    def test_mixed_batch_metrics_partition_is_mutually_exclusive(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            (ingestion_dir / "Manual" / "new.py").write_bytes(b"x = 1\n")
            (ingestion_dir / "Manual" / "doc.pdf").write_bytes(b"%PDF")
            (ingestion_dir / "Manual" / "weird.bin").write_bytes(b"\x00")

            source_entries = {
                "Manual/new.py": _source_entry("Manual/new.py", sha256=_hash(b"x = 1\n")),
                "Manual/doc.pdf": _source_entry("Manual/doc.pdf", sha256=_hash(b"%PDF")),
                "Manual/weird.bin": _source_entry("Manual/weird.bin", sha256=_hash(b"\x00")),
            }

            result = classify_normalization(
                source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            all_classified = (
                result.converted_new
                + result.converted_stale
                + result.converted_stale_converter
                + result.unchanged
                + [f.relative_path for f in result.failed]
                + result.deferred
                + result.unsupported
            )
            self.assertEqual(sorted(all_classified), sorted(source_entries.keys()))
            self.assertEqual(len(all_classified), len(set(all_classified)))


class FailureDiagnosticsTests(unittest.TestCase):
    def test_failed_conversion_records_the_converter_that_was_attempted(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            bad_bytes = b"\xff\xfe\x00broken"
            (ingestion_dir / "Manual" / "a.txt").write_bytes(bad_bytes)

            source_entries = {
                "Manual/a.txt": _source_entry("Manual/a.txt", sha256=_hash(bad_bytes))
            }

            result = classify_normalization(
                source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(len(result.failed), 1)
            self.assertEqual(result.failed[0].converter_id, CONVERTER_ID)
            self.assertEqual(result.failed[0].error_type, "UnicodeDecodeError")

    def test_os_error_reason_never_leaks_the_absolute_ingestion_path(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            # A directory where a file is expected triggers IsADirectoryError,
            # whose message embeds the absolute path -- exactly the case the
            # sanitizer exists for.
            (ingestion_dir / "Manual" / "a.txt").mkdir(parents=True)

            source_entries = {
                "Manual/a.txt": _source_entry("Manual/a.txt", sha256="0" * 64)
            }

            result = classify_normalization(
                source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(len(result.failed), 1)
            failure = result.failed[0]
            self.assertEqual(failure.error_type, "IsADirectoryError")
            self.assertNotIn(str(tmp), failure.reason)
            self.assertNotIn(str(ingestion_dir), failure.reason)
            self.assertIn("Manual/a.txt", failure.reason)

    def test_failure_reason_never_contains_document_content(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            secret_marker = "TOTALLY-SECRET-DOCUMENT-CONTENT"
            bad_bytes = f"{secret_marker}\xff\xfe".encode("latin-1")
            (ingestion_dir / "Manual" / "a.txt").write_bytes(bad_bytes)

            source_entries = {
                "Manual/a.txt": _source_entry("Manual/a.txt", sha256=_hash(bad_bytes))
            }

            result = classify_normalization(
                source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(len(result.failed), 1)
            self.assertNotIn(secret_marker, result.failed[0].reason)


class DocumentIdTests(unittest.TestCase):
    def test_new_document_is_assigned_a_fresh_uuid4(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            content = b"print(1)\n"
            (ingestion_dir / "Manual" / "a.py").write_bytes(content)

            source_entries = {"Manual/a.py": _source_entry("Manual/a.py", sha256=_hash(content))}

            result = classify_normalization(
                source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            document_id = result.curated_entries["Manual/a.py"].document_id
            self.assertTrue(document_id)
            self.assertEqual(uuid.UUID(document_id).version, 4)

    def test_two_new_documents_get_distinct_document_ids(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            (ingestion_dir / "Manual" / "a.py").write_bytes(b"a = 1\n")
            (ingestion_dir / "Manual" / "b.py").write_bytes(b"b = 2\n")

            source_entries = {
                "Manual/a.py": _source_entry("Manual/a.py", sha256=_hash(b"a = 1\n")),
                "Manual/b.py": _source_entry("Manual/b.py", sha256=_hash(b"b = 2\n")),
            }

            result = classify_normalization(
                source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertNotEqual(
                result.curated_entries["Manual/a.py"].document_id,
                result.curated_entries["Manual/b.py"].document_id,
            )

    def test_unchanged_document_keeps_its_previous_document_id(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            content = b"hello\n"
            (ingestion_dir / "Manual" / "a.txt").write_bytes(content)
            sha = _hash(content)

            previous = {
                "Manual/a.txt": _curated_entry(
                    "Manual/a.txt", source_sha256=sha, document_id="prev-document-id"
                )
            }
            source_entries = {"Manual/a.txt": _source_entry("Manual/a.txt", sha256=sha)}

            result = classify_normalization(
                source_entries, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.curated_entries["Manual/a.txt"].document_id, "prev-document-id")

    def test_converted_stale_preserves_previous_document_id(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            new_content = b"new content\n"
            (ingestion_dir / "Manual" / "a.txt").write_bytes(new_content)

            previous = {
                "Manual/a.txt": _curated_entry(
                    "Manual/a.txt",
                    source_sha256=_hash(b"old content\n"),
                    document_id="prev-document-id",
                )
            }
            source_entries = {
                "Manual/a.txt": _source_entry("Manual/a.txt", sha256=_hash(new_content))
            }

            result = classify_normalization(
                source_entries, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.converted_stale, ["Manual/a.txt"])
            self.assertEqual(result.curated_entries["Manual/a.txt"].document_id, "prev-document-id")

    def test_converted_stale_converter_preserves_previous_document_id(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            content = b"same content\n"
            (ingestion_dir / "Manual" / "a.txt").write_bytes(content)
            sha = _hash(content)

            previous = {
                "Manual/a.txt": _curated_entry(
                    "Manual/a.txt",
                    source_sha256=sha,
                    converter_version="0.0.1-old",
                    document_id="prev-document-id",
                )
            }
            source_entries = {"Manual/a.txt": _source_entry("Manual/a.txt", sha256=sha)}

            result = classify_normalization(
                source_entries, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.converted_stale_converter, ["Manual/a.txt"])
            self.assertEqual(result.curated_entries["Manual/a.txt"].document_id, "prev-document-id")

    def test_failed_document_with_previous_entry_preserves_document_id(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            bad_bytes = b"\xff\xfe\x00broken"
            (ingestion_dir / "Manual" / "a.txt").write_bytes(bad_bytes)

            previous = {
                "Manual/a.txt": _curated_entry(
                    "Manual/a.txt", source_sha256=_hash(b"old"), document_id="prev-document-id"
                )
            }
            source_entries = {
                "Manual/a.txt": _source_entry("Manual/a.txt", sha256=_hash(bad_bytes))
            }

            result = classify_normalization(
                source_entries, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(len(result.failed), 1)
            self.assertEqual(result.curated_entries["Manual/a.txt"].document_id, "prev-document-id")

    def test_orphaned_entry_keeps_its_document_id(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            ingestion_dir.mkdir(parents=True)

            previous = {
                "Manual/gone.txt": _curated_entry(
                    "Manual/gone.txt", source_sha256=_hash(b"x"), document_id="prev-document-id"
                )
            }

            result = classify_normalization(
                {}, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.orphaned, ["Manual/gone.txt"])
            self.assertEqual(
                result.curated_entries["Manual/gone.txt"].document_id, "prev-document-id"
            )


class DocumentTypeTests(unittest.TestCase):
    def test_each_known_knowledge_source_maps_to_its_document_type(self) -> None:
        expected = {
            "OneDrive-Proposals": "proposal",
            "OneDrive-Marketing": "marketing",
            "OneDrive-Portfolio": "portfolio",
        }
        for knowledge_source, expected_type in expected.items():
            with self.subTest(knowledge_source=knowledge_source):
                with TemporaryDirectory() as tmp:
                    ingestion_dir = Path(tmp) / "01-Ingestion"
                    markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
                    (ingestion_dir / knowledge_source).mkdir(parents=True)
                    content = b"hello\n"
                    (ingestion_dir / knowledge_source / "a.txt").write_bytes(content)

                    source_entries = {
                        f"{knowledge_source}/a.txt": _source_entry(
                            f"{knowledge_source}/a.txt",
                            sha256=_hash(content),
                            knowledge_source=knowledge_source,
                        )
                    }

                    result = classify_normalization(
                        source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                        run_timestamp=RUN_TS, dry_run=False,
                    )

                    entry = result.curated_entries[f"{knowledge_source}/a.txt"]
                    self.assertEqual(entry.document_type, expected_type)

    def test_unmapped_knowledge_source_maps_to_unknown(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "SomeOtherSource").mkdir(parents=True)
            content = b"hello\n"
            (ingestion_dir / "SomeOtherSource" / "a.txt").write_bytes(content)

            source_entries = {
                "SomeOtherSource/a.txt": _source_entry(
                    "SomeOtherSource/a.txt",
                    sha256=_hash(content),
                    knowledge_source="SomeOtherSource",
                )
            }

            result = classify_normalization(
                source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(
                result.curated_entries["SomeOtherSource/a.txt"].document_type, "unknown"
            )

    def test_converted_stale_recomputes_document_type_from_current_knowledge_source(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "OneDrive-Proposals").mkdir(parents=True)
            new_content = b"new content\n"
            (ingestion_dir / "OneDrive-Proposals" / "a.txt").write_bytes(new_content)

            # Previous entry deliberately carries a stale/incorrect document_type
            # to prove reconversion recomputes it rather than blindly reusing it.
            previous = {
                "OneDrive-Proposals/a.txt": _curated_entry(
                    "OneDrive-Proposals/a.txt",
                    source_sha256=_hash(b"old content\n"),
                    knowledge_source="OneDrive-Proposals",
                    document_type="unknown",
                )
            }
            source_entries = {
                "OneDrive-Proposals/a.txt": _source_entry(
                    "OneDrive-Proposals/a.txt",
                    sha256=_hash(new_content),
                    knowledge_source="OneDrive-Proposals",
                )
            }

            result = classify_normalization(
                source_entries, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.converted_stale, ["OneDrive-Proposals/a.txt"])
            self.assertEqual(
                result.curated_entries["OneDrive-Proposals/a.txt"].document_type, "proposal"
            )

    def test_unchanged_document_keeps_its_previous_document_type(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            content = b"hello\n"
            (ingestion_dir / "Manual" / "a.txt").write_bytes(content)
            sha = _hash(content)

            previous = {
                "Manual/a.txt": _curated_entry(
                    "Manual/a.txt", source_sha256=sha, document_type="marketing"
                )
            }
            source_entries = {"Manual/a.txt": _source_entry("Manual/a.txt", sha256=sha)}

            result = classify_normalization(
                source_entries, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.unchanged, ["Manual/a.txt"])
            self.assertEqual(result.curated_entries["Manual/a.txt"].document_type, "marketing")

    def test_orphaned_entry_keeps_its_document_type(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            ingestion_dir.mkdir(parents=True)

            previous = {
                "Manual/gone.txt": _curated_entry(
                    "Manual/gone.txt", source_sha256=_hash(b"x"), document_type="portfolio"
                )
            }

            result = classify_normalization(
                {}, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.orphaned, ["Manual/gone.txt"])
            self.assertEqual(
                result.curated_entries["Manual/gone.txt"].document_type, "portfolio"
            )


class DocumentLanguageTests(unittest.TestCase):
    SPANISH_CONTENT = (
        b"El documento describe la propuesta para el cliente y el equipo "
        b"en la reunion de hoy.\n"
    )
    ENGLISH_CONTENT = (
        b"The document describes the proposal for the client and the "
        b"team in this meeting today.\n"
    )

    def test_new_document_computes_spanish_from_source_content(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            (ingestion_dir / "Manual" / "a.txt").write_bytes(self.SPANISH_CONTENT)

            source_entries = {
                "Manual/a.txt": _source_entry("Manual/a.txt", sha256=_hash(self.SPANISH_CONTENT))
            }

            result = classify_normalization(
                source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.curated_entries["Manual/a.txt"].language, "es")

    def test_new_document_computes_english_from_source_content(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            (ingestion_dir / "Manual" / "a.txt").write_bytes(self.ENGLISH_CONTENT)

            source_entries = {
                "Manual/a.txt": _source_entry("Manual/a.txt", sha256=_hash(self.ENGLISH_CONTENT))
            }

            result = classify_normalization(
                source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.curated_entries["Manual/a.txt"].language, "en")

    def test_new_document_with_too_little_text_is_undetermined(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            content = b"x = 1\n"
            (ingestion_dir / "Manual" / "a.py").write_bytes(content)

            source_entries = {"Manual/a.py": _source_entry("Manual/a.py", sha256=_hash(content))}

            result = classify_normalization(
                source_entries, {}, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.curated_entries["Manual/a.py"].language, "und")

    def test_converted_stale_recomputes_language_from_new_content(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            (ingestion_dir / "Manual" / "a.txt").write_bytes(self.ENGLISH_CONTENT)

            previous = {
                "Manual/a.txt": _curated_entry(
                    "Manual/a.txt",
                    source_sha256=_hash(self.SPANISH_CONTENT),
                    language="es",
                )
            }
            source_entries = {
                "Manual/a.txt": _source_entry("Manual/a.txt", sha256=_hash(self.ENGLISH_CONTENT))
            }

            result = classify_normalization(
                source_entries, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.converted_stale, ["Manual/a.txt"])
            self.assertEqual(result.curated_entries["Manual/a.txt"].language, "en")

    def test_converted_stale_converter_recomputes_language(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            (ingestion_dir / "Manual" / "a.txt").write_bytes(self.SPANISH_CONTENT)
            sha = _hash(self.SPANISH_CONTENT)

            previous = {
                "Manual/a.txt": _curated_entry(
                    "Manual/a.txt",
                    source_sha256=sha,
                    converter_version="0.0.1-old",
                    language="und",
                )
            }
            source_entries = {"Manual/a.txt": _source_entry("Manual/a.txt", sha256=sha)}

            result = classify_normalization(
                source_entries, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.converted_stale_converter, ["Manual/a.txt"])
            self.assertEqual(result.curated_entries["Manual/a.txt"].language, "es")

    def test_unchanged_document_keeps_its_previous_language(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            content = b"hello\n"
            (ingestion_dir / "Manual" / "a.txt").write_bytes(content)
            sha = _hash(content)

            previous = {
                "Manual/a.txt": _curated_entry("Manual/a.txt", source_sha256=sha, language="es")
            }
            source_entries = {"Manual/a.txt": _source_entry("Manual/a.txt", sha256=sha)}

            result = classify_normalization(
                source_entries, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.unchanged, ["Manual/a.txt"])
            self.assertEqual(result.curated_entries["Manual/a.txt"].language, "es")

    def test_failed_document_with_previous_entry_preserves_language(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            (ingestion_dir / "Manual").mkdir(parents=True)
            bad_bytes = b"\xff\xfe\x00broken"
            (ingestion_dir / "Manual" / "a.txt").write_bytes(bad_bytes)

            previous = {
                "Manual/a.txt": _curated_entry(
                    "Manual/a.txt", source_sha256=_hash(b"old"), language="en"
                )
            }
            source_entries = {
                "Manual/a.txt": _source_entry("Manual/a.txt", sha256=_hash(bad_bytes))
            }

            result = classify_normalization(
                source_entries, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(len(result.failed), 1)
            self.assertEqual(result.curated_entries["Manual/a.txt"].language, "en")

    def test_orphaned_entry_keeps_its_language(self) -> None:
        with TemporaryDirectory() as tmp:
            ingestion_dir = Path(tmp) / "01-Ingestion"
            markdown_dir = Path(tmp) / "02-Curated" / "Markdown"
            ingestion_dir.mkdir(parents=True)

            previous = {
                "Manual/gone.txt": _curated_entry(
                    "Manual/gone.txt", source_sha256=_hash(b"x"), language="es"
                )
            }

            result = classify_normalization(
                {}, previous, ingestion_dir=ingestion_dir, markdown_dir=markdown_dir,
                run_timestamp=RUN_TS, dry_run=False,
            )

            self.assertEqual(result.orphaned, ["Manual/gone.txt"])
            self.assertEqual(result.curated_entries["Manual/gone.txt"].language, "es")


if __name__ == "__main__":
    unittest.main()
