from __future__ import annotations

import os
import stat
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from knowledge_compiler.scanner import scan, scan_with_report


class ScanTests(unittest.TestCase):
    def test_scan_is_sorted_ignores_dotfiles_and_derives_knowledge_source(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ChatGPT").mkdir()
            (root / "ChatGPT" / "b.txt").write_text("b", encoding="utf-8")
            (root / "Claude").mkdir()
            (root / "Claude" / "a.txt").write_text("a", encoding="utf-8")
            (root / ".DS_Store").write_text("junk", encoding="utf-8")
            nested = root / "Claude" / "sub"
            nested.mkdir()
            (nested / "c.txt").write_text("c", encoding="utf-8")

            results = list(scan(root))

            self.assertEqual(
                [entry.relative_path for entry in results],
                ["ChatGPT/b.txt", "Claude/a.txt", "Claude/sub/c.txt"],
            )
            self.assertEqual(
                [entry.knowledge_source for entry in results],
                ["ChatGPT", "Claude", "Claude"],
            )

    def test_scan_missing_root_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"
            with self.assertRaises(NotADirectoryError):
                list(scan(missing))


class ScanWithReportTests(unittest.TestCase):
    def test_separates_eligible_excluded_and_failed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Manual").mkdir()
            (root / "Manual" / "a.txt").write_text("a", encoding="utf-8")
            (root / "Manual" / ".DS_Store").write_text("junk", encoding="utf-8")
            (root / "Manual" / "ghost.txt").symlink_to(root / "Manual" / "missing-target.txt")

            report = scan_with_report(root)

            self.assertEqual([f.relative_path for f in report.eligible], ["Manual/a.txt"])
            self.assertEqual(
                [(e.relative_path, e.reason) for e in report.excluded],
                [("Manual/.DS_Store", "ignored_filename")],
            )
            self.assertEqual([f.relative_path for f in report.failed], ["Manual/ghost.txt"])
            self.assertEqual(report.failed[0].error_type, "FileNotFoundError")

    def test_dotfile_excluded_with_dotfile_reason(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Manual").mkdir()
            (root / "Manual" / ".hidden.txt").write_text("x", encoding="utf-8")

            report = scan_with_report(root)

            self.assertEqual(len(report.eligible), 0)
            self.assertEqual(report.excluded[0].reason, "dotfile")

    def test_counts_are_consistent_with_discovered_definition(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Manual").mkdir()
            (root / "Manual" / "a.txt").write_text("a", encoding="utf-8")
            (root / "Manual" / "b.txt").write_text("b", encoding="utf-8")
            (root / "Manual" / ".DS_Store").write_text("junk", encoding="utf-8")

            report = scan_with_report(root)
            discovered = len(report.eligible) + len(report.excluded) + len(report.failed)

            self.assertEqual(discovered, 3)
            self.assertEqual(len(report.eligible), 2)
            self.assertEqual(len(report.excluded), 1)
            self.assertEqual(len(report.failed), 0)

    def test_missing_root_raises_immediately(self) -> None:
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"
            with self.assertRaises(NotADirectoryError):
                scan_with_report(missing)


@unittest.skipUnless(
    hasattr(os, "geteuid") and os.geteuid() != 0,
    "requires a POSIX filesystem and a non-root user so permission bits are enforced",
)
class UnreadableDirectoryTests(unittest.TestCase):
    """A directory os.walk cannot list (e.g. permission denied) must surface
    as an explicit ScanFailure rather than being silently dropped."""

    @contextmanager
    def _blocked(self, path: Path):
        # Restored before the enclosing TemporaryDirectory tears down (rather
        # than via addCleanup/tearDown, which would run too late -- and
        # unlike relying on TemporaryDirectory's own permission-error repair
        # on cleanup, this keeps the fixture's lifetime explicit).
        os.chmod(path, 0o000)
        try:
            yield
        finally:
            os.chmod(path, stat.S_IRWXU)

    def test_unreadable_directory_is_recorded_as_a_scan_failure(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Manual").mkdir()
            (root / "Manual" / "a.txt").write_text("a", encoding="utf-8")
            blocked = root / "Manual" / "blocked"
            blocked.mkdir()
            (blocked / "hidden.txt").write_text("never seen", encoding="utf-8")

            with self._blocked(blocked):
                report = scan_with_report(root)

            self.assertEqual([f.relative_path for f in report.eligible], ["Manual/a.txt"])
            self.assertEqual([f.relative_path for f in report.failed], ["Manual/blocked"])
            self.assertEqual(report.failed[0].error_type, "PermissionError")
            # Contents of an unreadable directory are never visited, so they
            # cannot appear anywhere in the report.
            all_paths = (
                [f.relative_path for f in report.eligible]
                + [e.relative_path for e in report.excluded]
                + [f.relative_path for f in report.failed]
            )
            self.assertNotIn("Manual/blocked/hidden.txt", all_paths)

    def test_unreadable_directory_does_not_disrupt_sibling_scanning(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Claude").mkdir()
            (root / "Claude" / "a.txt").write_text("a", encoding="utf-8")
            blocked = root / "Claude" / "blocked"
            blocked.mkdir()
            (root / "OneDrive").mkdir()
            (root / "OneDrive" / "z.txt").write_text("z", encoding="utf-8")

            with self._blocked(blocked):
                report = scan_with_report(root)

            self.assertEqual(
                [f.relative_path for f in report.eligible],
                ["Claude/a.txt", "OneDrive/z.txt"],
            )
            self.assertEqual([f.relative_path for f in report.failed], ["Claude/blocked"])
            # 2 eligible files + 1 failed directory + 0 excluded.
            discovered = len(report.eligible) + len(report.excluded) + len(report.failed)
            self.assertEqual(discovered, 3)

    def test_scan_report_is_deterministic_across_repeated_runs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Claude").mkdir()
            (root / "Claude" / "a.txt").write_text("a", encoding="utf-8")
            blocked = root / "Claude" / "blocked"
            blocked.mkdir()
            (root / "OneDrive").mkdir()
            (root / "OneDrive" / "z.txt").write_text("z", encoding="utf-8")

            with self._blocked(blocked):
                first = scan_with_report(root)
                second = scan_with_report(root)

            self.assertEqual(
                [f.relative_path for f in first.eligible],
                [f.relative_path for f in second.eligible],
            )
            self.assertEqual(
                [(f.relative_path, f.error_type) for f in first.failed],
                [(f.relative_path, f.error_type) for f in second.failed],
            )


if __name__ == "__main__":
    unittest.main()
