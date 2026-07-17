from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from knowledge_compiler.metadata import build_document_metadata, extract_metadata
from knowledge_compiler.scanner import scan


class ExtractMetadataTests(unittest.TestCase):
    def test_hash_matches_known_content(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "Manual"
            source_dir.mkdir()
            content = b"ai hub knowledge compiler"
            (source_dir / "doc.txt").write_bytes(content)

            [scanned] = list(scan(root))
            metadata = extract_metadata(scanned)

            self.assertEqual(metadata.sha256, hashlib.sha256(content).hexdigest())
            self.assertEqual(metadata.size_bytes, len(content))
            self.assertEqual(metadata.extension, ".txt")
            self.assertEqual(metadata.file_name, "doc.txt")
            self.assertEqual(metadata.knowledge_source, "Manual")
            self.assertEqual(metadata.relative_path, "Manual/doc.txt")

    def test_same_content_produces_same_hash(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "Manual"
            source_dir.mkdir()
            (source_dir / "one.txt").write_bytes(b"same content")
            (source_dir / "two.txt").write_bytes(b"same content")

            hashes = {extract_metadata(f).sha256 for f in scan(root)}

            self.assertEqual(len(hashes), 1)

    def test_lifecycle_fields_default_to_now_when_not_provided(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "Manual"
            source_dir.mkdir()
            (source_dir / "doc.txt").write_bytes(b"content")

            [scanned] = list(scan(root))
            metadata = extract_metadata(scanned)

            self.assertTrue(metadata.first_seen_at)
            self.assertTrue(metadata.last_verified_at)

    def test_lifecycle_fields_can_be_overridden(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "Manual"
            source_dir.mkdir()
            (source_dir / "doc.txt").write_bytes(b"content")

            [scanned] = list(scan(root))
            metadata = extract_metadata(
                scanned,
                first_seen_at="2020-01-01T00:00:00+00:00",
                last_verified_at="2021-01-01T00:00:00+00:00",
            )

            self.assertEqual(metadata.first_seen_at, "2020-01-01T00:00:00+00:00")
            self.assertEqual(metadata.last_verified_at, "2021-01-01T00:00:00+00:00")


class BuildDocumentMetadataTests(unittest.TestCase):
    def test_uses_precomputed_hash_without_reading_file_content(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "Manual"
            source_dir.mkdir()
            (source_dir / "doc.txt").write_bytes(b"irrelevant to this test")

            [scanned] = list(scan(root))
            metadata = build_document_metadata(
                scanned,
                sha256="deadbeef" * 8,
                first_seen_at="2020-01-01T00:00:00+00:00",
                last_verified_at="2020-01-01T00:00:00+00:00",
            )

            self.assertEqual(metadata.sha256, "deadbeef" * 8)
            self.assertEqual(metadata.first_seen_at, "2020-01-01T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
