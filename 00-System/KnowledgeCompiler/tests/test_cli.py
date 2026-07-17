from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from knowledge_compiler.cli import EXIT_CLEAN, EXIT_DEGRADED, EXIT_HARD_STOP, main, run


def _make_repo(root: Path) -> None:
    config = {
        "platform": {"name": "AI Hub", "version": "0.1.0", "execution_mode": "local"},
        "storage": {"type": "local-filesystem", "root": "."},
        "folders": {"ingestion": "01-Ingestion", "indexes": "08-Indexes"},
    }
    (root / "aihub.json").write_text(json.dumps(config), encoding="utf-8")
    (root / "01-Ingestion" / "Manual").mkdir(parents=True)
    (root / "01-Ingestion" / "Manual" / "a.txt").write_bytes(b"hello")


class DryRunTests(unittest.TestCase):
    def test_dry_run_writes_no_files_on_a_fresh_repository(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)

            result = run(root, dry_run=True)

            self.assertEqual(result.exit_code, EXIT_CLEAN)
            self.assertFalse((root / "08-Indexes").exists())
            self.assertIsNone(result.document_manifest_path)
            self.assertIsNone(result.run_metadata_path)
            self.assertIsNone(result.run_history_path)

    def test_dry_run_after_a_real_run_creates_no_new_run_history_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            run(root)  # establishes a baseline manifest + one run-history file

            runs_dir = root / "08-Indexes" / "Metadata" / "runs"
            before = set(p.name for p in runs_dir.iterdir())

            result = run(root, dry_run=True)

            after = set(p.name for p in runs_dir.iterdir())
            self.assertEqual(before, after)
            self.assertEqual(result.exit_code, EXIT_CLEAN)

    def test_dry_run_does_not_modify_existing_manifest_content(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            run(root)
            manifest_path = root / "08-Indexes" / "Metadata" / "document_manifest.jsonl"
            before = manifest_path.read_text(encoding="utf-8")

            (root / "01-Ingestion" / "Manual" / "b.txt").write_bytes(b"a new file")
            run(root, dry_run=True)

            self.assertEqual(manifest_path.read_text(encoding="utf-8"), before)


class NormalRunTests(unittest.TestCase):
    def test_writes_three_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)

            result = run(root)

            self.assertEqual(result.exit_code, EXIT_CLEAN)
            self.assertTrue(result.document_manifest_path.is_file())
            self.assertTrue(result.run_metadata_path.is_file())
            self.assertTrue(result.run_history_path.is_file())
            self.assertEqual(result.metrics["new"], 1)

    def test_second_run_is_incremental_and_reuses_hash(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            run(root)

            result = run(root)

            self.assertEqual(result.metrics["hashes_reused"], 1)
            self.assertEqual(result.metrics["hashes_recomputed"], 0)
            self.assertEqual(result.metrics["unchanged"], 1)
            self.assertEqual(result.metrics["new"], 0)

    def test_full_forces_rehash_but_keeps_classification(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            run(root)

            result = run(root, force_full=True)

            self.assertEqual(result.metrics["hashes_recomputed"], 1)
            self.assertEqual(result.metrics["hashes_reused"], 0)
            self.assertEqual(result.metrics["unchanged"], 1)
            self.assertEqual(result.metrics["new"], 0)


class DiscoveredEligibleExcludedTests(unittest.TestCase):
    def test_counts_separate_policy_exclusions_from_eligible_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            (root / "01-Ingestion" / "Manual" / ".DS_Store").write_bytes(b"junk")

            result = run(root, dry_run=True)

            self.assertEqual(result.metrics["eligible"], 1)
            self.assertEqual(result.metrics["excluded"], 1)
            self.assertEqual(result.metrics["discovered"], 2)


class DegradedRunTests(unittest.TestCase):
    def test_broken_symlink_yields_exit_code_two_and_no_deletion(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            (root / "01-Ingestion" / "Manual" / "ghost.txt").symlink_to(
                root / "01-Ingestion" / "Manual" / "does-not-exist.txt"
            )

            result = run(root)

            self.assertEqual(result.exit_code, EXIT_DEGRADED)
            self.assertEqual(result.metrics["failed"], 1)
            self.assertEqual(result.metrics["deleted"], 0)
            self.assertEqual(result.metrics["new"], 1)  # a.txt still processed normally

    def test_degraded_run_still_publishes_all_three_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            (root / "01-Ingestion" / "Manual" / "ghost.txt").symlink_to(
                root / "01-Ingestion" / "Manual" / "does-not-exist.txt"
            )

            result = run(root)

            self.assertTrue(result.document_manifest_path.is_file())
            self.assertTrue(result.run_metadata_path.is_file())
            self.assertTrue(result.run_history_path.is_file())


class RunIdCollisionTests(unittest.TestCase):
    def test_repeated_runs_produce_distinct_run_history_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)

            first = run(root)
            second = run(root)

            self.assertNotEqual(first.run_history_path.name, second.run_history_path.name)
            self.assertTrue(first.run_history_path.is_file())
            self.assertTrue(second.run_history_path.is_file())


class CorruptManifestTests(unittest.TestCase):
    def test_corrupt_manifest_without_full_stops_and_writes_nothing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            manifest_dir = root / "08-Indexes" / "Metadata"
            manifest_dir.mkdir(parents=True)
            manifest_path = manifest_dir / "document_manifest.jsonl"
            manifest_path.write_text("{not valid json\n", encoding="utf-8")

            result = run(root)

            self.assertEqual(result.exit_code, EXIT_HARD_STOP)
            self.assertIsNone(result.document_manifest_path)
            self.assertEqual(manifest_path.read_text(encoding="utf-8"), "{not valid json\n")
            self.assertFalse((manifest_dir / "runs").exists())

    def test_corrupt_manifest_with_full_backs_up_and_recovers(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            manifest_dir = root / "08-Indexes" / "Metadata"
            manifest_dir.mkdir(parents=True)
            manifest_path = manifest_dir / "document_manifest.jsonl"
            manifest_path.write_text("{not valid json\n", encoding="utf-8")

            result = run(root, force_full=True)

            self.assertEqual(result.exit_code, EXIT_CLEAN)
            backups = list(manifest_dir.glob("document_manifest.jsonl.corrupt-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "{not valid json\n")
            self.assertEqual(
                json.loads(manifest_path.read_text(encoding="utf-8").splitlines()[0])[
                    "relative_path"
                ],
                "Manual/a.txt",
            )


class CliMainTests(unittest.TestCase):
    def test_main_dry_run_flag_returns_clean_exit_and_writes_nothing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)

            exit_code = main(["--root", str(root), "--dry-run"])

            self.assertEqual(exit_code, EXIT_CLEAN)
            self.assertFalse((root / "08-Indexes").exists())

    def test_main_normal_run_returns_clean_exit_and_writes_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)

            exit_code = main(["--root", str(root)])

            self.assertEqual(exit_code, EXIT_CLEAN)
            self.assertTrue((root / "08-Indexes" / "Metadata" / "document_manifest.jsonl").is_file())

    def test_main_returns_hard_stop_on_missing_ingestion_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {
                "platform": {"name": "AI Hub", "version": "0.1.0", "execution_mode": "local"},
                "storage": {"type": "local-filesystem", "root": "."},
                "folders": {"ingestion": "01-Ingestion", "indexes": "08-Indexes"},
            }
            (root / "aihub.json").write_text(json.dumps(config), encoding="utf-8")

            exit_code = main(["--root", str(root)])

            self.assertEqual(exit_code, EXIT_HARD_STOP)


if __name__ == "__main__":
    unittest.main()
