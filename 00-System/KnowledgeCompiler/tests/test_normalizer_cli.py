from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from knowledge_compiler import cli as compiler_cli
from knowledge_compiler import converters
from knowledge_compiler.normalizer_cli import (
    EXIT_CLEAN,
    EXIT_DEGRADED,
    EXIT_HARD_STOP,
    SourceManifestMissingError,
    main,
    run,
)


def _make_repo(root: Path) -> None:
    config = {
        "platform": {"name": "AI Hub", "version": "0.1.0", "execution_mode": "local"},
        "storage": {"type": "local-filesystem", "root": "."},
        "folders": {
            "ingestion": "01-Ingestion",
            "indexes": "08-Indexes",
            "curated": "02-Curated",
        },
    }
    (root / "aihub.json").write_text(json.dumps(config), encoding="utf-8")
    (root / "01-Ingestion" / "Manual").mkdir(parents=True)
    (root / "01-Ingestion" / "Manual" / "a.py").write_bytes(b"print('hi')\n")


class SourceManifestRequiredTests(unittest.TestCase):
    def test_missing_v11_manifest_raises_without_writing_anything(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)

            with self.assertRaises(SourceManifestMissingError):
                run(root)

            self.assertFalse((root / "02-Curated").exists())


class NormalizeRunTests(unittest.TestCase):
    def test_first_run_converts_text_native_document(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            compiler_cli.run(root)  # V1.1 scan establishes the source manifest

            result = run(root)

            self.assertEqual(result.exit_code, EXIT_CLEAN)
            self.assertEqual(result.metrics["converted_new"], 1)
            self.assertTrue(result.curated_manifest_path.is_file())
            self.assertTrue(result.run_metadata_path.is_file())
            self.assertTrue(result.run_history_path.is_file())

            output_path = root / "02-Curated" / "Markdown" / "Manual" / "a.py.md"
            self.assertTrue(output_path.is_file())
            markdown = output_path.read_text(encoding="utf-8")
            self.assertIn("print('hi')", markdown)

    def test_second_run_is_incremental_and_leaves_output_untouched(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            compiler_cli.run(root)
            run(root)

            output_path = root / "02-Curated" / "Markdown" / "Manual" / "a.py.md"
            before_mtime = output_path.stat().st_mtime_ns

            result = run(root)

            self.assertEqual(result.metrics["unchanged"], 1)
            self.assertEqual(result.metrics["converted_new"], 0)
            self.assertEqual(output_path.stat().st_mtime_ns, before_mtime)

    def test_dry_run_writes_nothing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            compiler_cli.run(root)

            result = run(root, dry_run=True)

            self.assertEqual(result.metrics["converted_new"], 1)
            self.assertFalse((root / "02-Curated").exists())
            self.assertIsNone(result.curated_manifest_path)

    def test_source_change_triggers_converted_stale_on_next_run(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            compiler_cli.run(root)
            run(root)

            (root / "01-Ingestion" / "Manual" / "a.py").write_bytes(b"print('changed')\n")
            compiler_cli.run(root)

            result = run(root)

            self.assertEqual(result.metrics["converted_stale"], 1)

    def test_converter_version_bump_triggers_stale_converter_reconversion(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            compiler_cli.run(root)
            run(root)

            original_version = converters.CONVERTER_VERSION
            try:
                converters.CONVERTER_VERSION = "9.9.9-test"
                result = run(root)
            finally:
                converters.CONVERTER_VERSION = original_version

            self.assertEqual(result.metrics["converted_stale_converter"], 1)

    def test_degraded_run_preserves_previous_entry_and_exits_two(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            compiler_cli.run(root)
            run(root)

            # Corrupt the source bytes so the second normalize run fails to decode it.
            (root / "01-Ingestion" / "Manual" / "a.py").write_bytes(b"\xff\xfe broken\n")
            compiler_cli.run(root)

            result = run(root)

            self.assertEqual(result.exit_code, EXIT_DEGRADED)
            self.assertEqual(result.metrics["failed"], 1)
            self.assertTrue(result.curated_manifest_path.is_file())
            manifest_lines = result.curated_manifest_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(manifest_lines), 1)  # previous entry preserved, not dropped

            self.assertEqual(len(result.failures), 1)
            failure = result.failures[0]
            self.assertEqual(failure["relative_path"], "Manual/a.py")
            self.assertEqual(failure["converter_id"], "text_native")
            self.assertEqual(failure["error_type"], "UnicodeDecodeError")
            self.assertNotIn(str(root), failure["reason"])

    def test_degraded_run_metadata_and_history_report_identical_failure_details(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            compiler_cli.run(root)
            run(root)

            (root / "01-Ingestion" / "Manual" / "a.py").write_bytes(b"\xff\xfe broken\n")
            compiler_cli.run(root)

            result = run(root)

            run_metadata = json.loads(result.run_metadata_path.read_text(encoding="utf-8"))
            run_history = json.loads(result.run_history_path.read_text(encoding="utf-8"))

            self.assertEqual(run_metadata["failed"], run_history["failed"])
            self.assertEqual(len(run_metadata["failed"]), 1)
            self.assertEqual(run_metadata["failed"][0]["relative_path"], "Manual/a.py")
            self.assertNotIn(str(root), run_metadata["failed"][0]["reason"])

    def test_dry_run_reports_failures_without_writing_anything(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            compiler_cli.run(root)
            run(root)

            (root / "01-Ingestion" / "Manual" / "a.py").write_bytes(b"\xff\xfe broken\n")
            compiler_cli.run(root)

            result = run(root, dry_run=True)

            self.assertEqual(result.exit_code, EXIT_DEGRADED)
            self.assertEqual(len(result.failures), 1)
            self.assertIsNone(result.curated_manifest_path)

    def test_orphaned_entry_survives_when_source_document_is_deleted(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            compiler_cli.run(root)
            run(root)

            (root / "01-Ingestion" / "Manual" / "a.py").unlink()
            compiler_cli.run(root)

            result = run(root)

            self.assertEqual(result.metrics["orphaned"], 1)
            output_path = root / "02-Curated" / "Markdown" / "Manual" / "a.py.md"
            self.assertTrue(output_path.is_file())  # output left untouched


class NormalizeCliMainTests(unittest.TestCase):
    def test_main_dry_run_returns_clean_exit_and_writes_nothing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            compiler_cli.run(root)

            exit_code = main(["--root", str(root), "--dry-run"])

            self.assertEqual(exit_code, EXIT_CLEAN)
            self.assertFalse((root / "02-Curated").exists())

    def test_main_returns_hard_stop_when_v11_manifest_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)

            exit_code = main(["--root", str(root)])

            self.assertEqual(exit_code, EXIT_HARD_STOP)

    def test_main_prints_failures_section_on_degraded_run(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            compiler_cli.run(root)
            main(["--root", str(root)])

            (root / "01-Ingestion" / "Manual" / "a.py").write_bytes(b"\xff\xfe broken\n")
            compiler_cli.run(root)

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = main(["--root", str(root)])
            output = buffer.getvalue()
            failures_section = output.split("Failures:", 1)[1]

            self.assertEqual(exit_code, EXIT_DEGRADED)
            self.assertIn("Failures:", output)
            self.assertIn("Manual/a.py", output)
            self.assertIn("text_native", output)
            self.assertIn("UnicodeDecodeError", output)
            # The failure line itself must stay relative-path-only; the
            # "written to <path>" lines further down legitimately print
            # absolute output locations and are excluded from this check.
            failure_line = failures_section.strip().splitlines()[0]
            self.assertNotIn(str(root), failure_line)

    def test_main_prints_failures_section_on_degraded_dry_run(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            compiler_cli.run(root)
            main(["--root", str(root)])
            manifest_path = root / "02-Curated" / "Metadata" / "document_normalizer_manifest.jsonl"
            before = manifest_path.read_text(encoding="utf-8")

            (root / "01-Ingestion" / "Manual" / "a.py").write_bytes(b"\xff\xfe broken\n")
            compiler_cli.run(root)

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = main(["--root", str(root), "--dry-run"])
            output = buffer.getvalue()

            self.assertEqual(exit_code, EXIT_DEGRADED)
            self.assertIn("Failures:", output)
            self.assertIn("Manual/a.py", output)
            self.assertIn("Dry run: no files were written.", output)
            # The dry run must not touch the curated manifest left by the
            # earlier real run.
            self.assertEqual(manifest_path.read_text(encoding="utf-8"), before)

    def test_main_prints_no_failures_section_on_clean_run(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            compiler_cli.run(root)

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = main(["--root", str(root)])
            output = buffer.getvalue()

            self.assertEqual(exit_code, EXIT_CLEAN)
            self.assertNotIn("Failures:", output)


class DispatchFromTopLevelCliTests(unittest.TestCase):
    def test_normalize_subcommand_dispatches_through_top_level_cli(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            compiler_cli.run(root)

            exit_code = compiler_cli.main(["normalize", "--root", str(root), "--dry-run"])

            self.assertEqual(exit_code, EXIT_CLEAN)
            self.assertFalse((root / "02-Curated").exists())

    def test_existing_scan_argv_shapes_are_unaffected_by_the_dispatch(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)

            exit_code = compiler_cli.main(["--root", str(root), "--dry-run"])

            self.assertEqual(exit_code, compiler_cli.EXIT_CLEAN)
            self.assertFalse((root / "08-Indexes").exists())


if __name__ == "__main__":
    unittest.main()
