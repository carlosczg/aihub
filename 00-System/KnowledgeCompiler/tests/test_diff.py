from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from knowledge_compiler.diff import classify
from knowledge_compiler.metadata import DocumentMetadata, modified_at_iso
from knowledge_compiler.scanner import ScanFailure, scan

RUN_TS = "2026-07-16T00:00:00+00:00"


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _prev(
    relative_path: str,
    *,
    size_bytes: int,
    modified_at: str,
    sha256: str,
) -> DocumentMetadata:
    return DocumentMetadata(
        relative_path=relative_path,
        file_name=Path(relative_path).name,
        extension=Path(relative_path).suffix,
        size_bytes=size_bytes,
        modified_at=modified_at,
        knowledge_source=relative_path.split("/")[0],
        sha256=sha256,
        mime_type="text/plain",
        first_seen_at=RUN_TS,
        last_verified_at=RUN_TS,
    )


class ClassifyTests(unittest.TestCase):
    def test_new_modified_unchanged_and_deleted(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Manual").mkdir()
            (root / "Manual" / "unchanged.txt").write_bytes(b"same content")
            (root / "Manual" / "modified.txt").write_bytes(b"new content")
            (root / "Manual" / "new.txt").write_bytes(b"brand new")

            scanned_by_path = {f.relative_path: f for f in scan(root)}
            unchanged_scanned = scanned_by_path["Manual/unchanged.txt"]

            previous = {
                "Manual/unchanged.txt": _prev(
                    "Manual/unchanged.txt",
                    size_bytes=unchanged_scanned.size_bytes,
                    modified_at=modified_at_iso(unchanged_scanned),
                    sha256=_hash(b"same content"),
                ),
                "Manual/modified.txt": _prev(
                    "Manual/modified.txt",
                    size_bytes=999,
                    modified_at="2000-01-01T00:00:00+00:00",
                    sha256=_hash(b"old content"),
                ),
                "Manual/removed.txt": _prev(
                    "Manual/removed.txt",
                    size_bytes=1,
                    modified_at=RUN_TS,
                    sha256="0" * 64,
                ),
            }

            result = classify(
                list(scanned_by_path.values()), previous, force_full=False, run_timestamp=RUN_TS
            )

            self.assertEqual(result.new, ["Manual/new.txt"])
            self.assertEqual(result.modified, ["Manual/modified.txt"])
            self.assertEqual(result.unchanged, ["Manual/unchanged.txt"])
            self.assertEqual(result.deleted, ["Manual/removed.txt"])
            self.assertEqual(result.hashes_reused, 1)
            self.assertEqual(result.hashes_recomputed, 2)
            self.assertEqual(
                result.manifest_entries["Manual/unchanged.txt"].first_seen_at, RUN_TS
            )

    def test_touched_file_with_unchanged_content_is_classified_unchanged(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Manual").mkdir()
            (root / "Manual" / "touched.txt").write_bytes(b"stable content")
            [scanned] = list(scan(root))

            previous = {
                "Manual/touched.txt": _prev(
                    "Manual/touched.txt",
                    size_bytes=scanned.size_bytes,
                    modified_at="2000-01-01T00:00:00+00:00",  # deliberately stale mtime
                    sha256=_hash(b"stable content"),
                ),
            }

            result = classify([scanned], previous, force_full=False, run_timestamp=RUN_TS)

            self.assertEqual(result.unchanged, ["Manual/touched.txt"])
            self.assertEqual(result.hashes_recomputed, 1)  # mtime drift forced verification
            self.assertEqual(result.hashes_reused, 0)

    def test_force_full_rehashes_but_preserves_classification(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Manual").mkdir()
            (root / "Manual" / "same.txt").write_bytes(b"identical")
            [scanned] = list(scan(root))

            previous = {
                "Manual/same.txt": _prev(
                    "Manual/same.txt",
                    size_bytes=scanned.size_bytes,
                    modified_at=modified_at_iso(scanned),
                    sha256=_hash(b"identical"),
                ),
            }

            incremental = classify([scanned], previous, force_full=False, run_timestamp=RUN_TS)
            full = classify([scanned], previous, force_full=True, run_timestamp=RUN_TS)

            self.assertEqual(incremental.new, full.new)
            self.assertEqual(incremental.modified, full.modified)
            self.assertEqual(incremental.unchanged, full.unchanged)
            self.assertEqual(incremental.unchanged, ["Manual/same.txt"])
            self.assertEqual(incremental.hashes_reused, 1)
            self.assertEqual(full.hashes_reused, 0)
            self.assertEqual(full.hashes_recomputed, 1)

    def test_force_full_with_no_previous_entry_is_still_new(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Manual").mkdir()
            (root / "Manual" / "brand_new.txt").write_bytes(b"content")
            [scanned] = list(scan(root))

            result = classify([scanned], {}, force_full=True, run_timestamp=RUN_TS)

            self.assertEqual(result.new, ["Manual/brand_new.txt"])
            self.assertEqual(result.modified, [])

    def test_hash_time_failure_preserves_previous_entry_and_is_not_deleted(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Manual").mkdir()
            ghost = root / "Manual" / "ghost.txt"
            ghost.write_bytes(b"will vanish")
            [scanned] = list(scan(root))
            ghost.unlink()  # file removed after stat, before hashing

            previous = {
                "Manual/ghost.txt": _prev(
                    "Manual/ghost.txt",
                    size_bytes=scanned.size_bytes,
                    modified_at="2000-01-01T00:00:00+00:00",  # forces need_hash
                    sha256="a" * 64,
                ),
            }

            result = classify([scanned], previous, force_full=False, run_timestamp=RUN_TS)

            self.assertEqual(result.new, [])
            self.assertEqual(result.modified, [])
            self.assertEqual(result.unchanged, [])
            self.assertEqual(result.deleted, [])
            self.assertEqual(len(result.failed), 1)
            failure = result.failed[0]
            self.assertEqual(failure.relative_path, "Manual/ghost.txt")
            self.assertTrue(failure.previous_entry_preserved)
            self.assertEqual(result.manifest_entries["Manual/ghost.txt"].sha256, "a" * 64)

    def test_failed_new_file_has_no_previous_entry_to_preserve(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Manual").mkdir()
            ghost = root / "Manual" / "brand_new_ghost.txt"
            ghost.write_bytes(b"short lived")
            [scanned] = list(scan(root))
            ghost.unlink()

            result = classify([scanned], {}, force_full=False, run_timestamp=RUN_TS)

            self.assertEqual(len(result.failed), 1)
            self.assertFalse(result.failed[0].previous_entry_preserved)
            self.assertNotIn("Manual/brand_new_ghost.txt", result.manifest_entries)

    def test_scan_time_failure_is_recorded_and_preserves_previous_entry(self) -> None:
        previous = {
            "Manual/broken_link.txt": _prev(
                "Manual/broken_link.txt",
                size_bytes=1,
                modified_at=RUN_TS,
                sha256="b" * 64,
            ),
        }
        scan_failures = [
            ScanFailure(
                relative_path="Manual/broken_link.txt",
                reason="[Errno 2] No such file or directory",
                error_type="FileNotFoundError",
            )
        ]

        result = classify(
            [], previous, force_full=False, run_timestamp=RUN_TS, scan_failures=scan_failures
        )

        self.assertEqual(len(result.failed), 1)
        self.assertTrue(result.failed[0].previous_entry_preserved)
        self.assertEqual(result.deleted, [])
        self.assertEqual(result.manifest_entries["Manual/broken_link.txt"].sha256, "b" * 64)

    def test_rename_is_delete_plus_add_with_no_correlation(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Manual").mkdir()
            (root / "Manual" / "renamed.txt").write_bytes(b"same bytes")
            [scanned] = list(scan(root))

            previous = {
                "Manual/original.txt": _prev(
                    "Manual/original.txt",
                    size_bytes=scanned.size_bytes,
                    modified_at=modified_at_iso(scanned),
                    sha256=_hash(b"same bytes"),
                ),
            }

            result = classify([scanned], previous, force_full=False, run_timestamp=RUN_TS)

            self.assertEqual(result.new, ["Manual/renamed.txt"])
            self.assertEqual(result.deleted, ["Manual/original.txt"])
            self.assertEqual(result.modified, [])


if __name__ == "__main__":
    unittest.main()
