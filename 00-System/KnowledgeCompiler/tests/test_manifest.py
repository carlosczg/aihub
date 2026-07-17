from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from knowledge_compiler.diff import ClassificationResult
from knowledge_compiler.manifest import (
    RUN_HISTORY_SUBDIR,
    ManifestCorruptError,
    backup_corrupt_manifest,
    build_run_history_payload,
    build_run_metadata_payload,
    load_previous_manifest,
    stage_and_publish_run,
    unique_run_id,
)
from knowledge_compiler.metadata import DocumentMetadata

RUN_TS = "2026-01-01T00:00:00+00:00"


def _entry(relative_path: str, knowledge_source: str = "Manual") -> DocumentMetadata:
    return DocumentMetadata(
        relative_path=relative_path,
        file_name=Path(relative_path).name,
        extension=Path(relative_path).suffix,
        size_bytes=1,
        modified_at=RUN_TS,
        knowledge_source=knowledge_source,
        sha256="0" * 64,
        mime_type="text/plain",
        first_seen_at=RUN_TS,
        last_verified_at=RUN_TS,
    )


def _empty_classification() -> ClassificationResult:
    return ClassificationResult(manifest_entries={})


def _clean_metrics(**overrides) -> dict:
    metrics = {
        "discovered": 0,
        "eligible": 0,
        "excluded": 0,
        "processed": 0,
        "new": 0,
        "modified": 0,
        "unchanged": 0,
        "deleted": 0,
        "failed": 0,
        "hashes_recomputed": 0,
        "hashes_reused": 0,
        "duration_seconds": 0.0,
    }
    metrics.update(overrides)
    return metrics


class LoadPreviousManifestTests(unittest.TestCase):
    def test_missing_file_is_valid_and_not_legacy(self) -> None:
        with TemporaryDirectory() as tmp:
            loaded = load_previous_manifest(Path(tmp) / "missing.jsonl", migration_timestamp=RUN_TS)
            self.assertEqual(loaded.entries, {})
            self.assertFalse(loaded.is_legacy)

    def test_valid_schema_v2_manifest_loads_without_backfill(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_manifest.jsonl"
            record = {
                "relative_path": "Manual/a.txt",
                "file_name": "a.txt",
                "extension": ".txt",
                "size_bytes": 1,
                "modified_at": "2020-01-01T00:00:00+00:00",
                "knowledge_source": "Manual",
                "sha256": "0" * 64,
                "mime_type": "text/plain",
                "first_seen_at": "2019-01-01T00:00:00+00:00",
                "last_verified_at": "2020-06-01T00:00:00+00:00",
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            loaded = load_previous_manifest(path, migration_timestamp=RUN_TS)

            self.assertFalse(loaded.is_legacy)
            entry = loaded.entries["Manual/a.txt"]
            self.assertEqual(entry.first_seen_at, "2019-01-01T00:00:00+00:00")
            self.assertEqual(entry.last_verified_at, "2020-06-01T00:00:00+00:00")

    def test_legacy_v1_manifest_backfills_lifecycle_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_manifest.jsonl"
            legacy_record = {
                "relative_path": "Manual/a.txt",
                "file_name": "a.txt",
                "extension": ".txt",
                "size_bytes": 1,
                "modified_at": "2020-01-01T00:00:00+00:00",
                "knowledge_source": "Manual",
                "sha256": "0" * 64,
                "mime_type": "text/plain",
            }
            path.write_text(json.dumps(legacy_record) + "\n", encoding="utf-8")

            loaded = load_previous_manifest(path, migration_timestamp=RUN_TS)

            self.assertTrue(loaded.is_legacy)
            entry = loaded.entries["Manual/a.txt"]
            self.assertEqual(entry.first_seen_at, RUN_TS)
            self.assertEqual(entry.last_verified_at, RUN_TS)

    def test_corrupt_json_line_raises_manifest_corrupt_error(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_manifest.jsonl"
            path.write_text("{not valid json\n", encoding="utf-8")

            with self.assertRaises(ManifestCorruptError):
                load_previous_manifest(path, migration_timestamp=RUN_TS)

    def test_missing_required_field_raises_manifest_corrupt_error(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_manifest.jsonl"
            path.write_text(json.dumps({"relative_path": "a.txt"}) + "\n", encoding="utf-8")

            with self.assertRaises(ManifestCorruptError):
                load_previous_manifest(path, migration_timestamp=RUN_TS)

    def test_duplicate_relative_path_raises_manifest_corrupt_error(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_manifest.jsonl"
            record = {
                "relative_path": "Manual/a.txt",
                "file_name": "a.txt",
                "extension": ".txt",
                "size_bytes": 1,
                "modified_at": RUN_TS,
                "knowledge_source": "Manual",
                "sha256": "0" * 64,
                "mime_type": "text/plain",
            }
            line = json.dumps(record)
            path.write_text(line + "\n" + line + "\n", encoding="utf-8")

            with self.assertRaises(ManifestCorruptError):
                load_previous_manifest(path, migration_timestamp=RUN_TS)


class BackupCorruptManifestTests(unittest.TestCase):
    def test_backup_copies_content_without_removing_original(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_manifest.jsonl"
            path.write_text("not json", encoding="utf-8")

            backup_path = backup_corrupt_manifest(path, run_id="20260101T000000.000000Z-abcd")

            self.assertTrue(path.exists())
            self.assertTrue(backup_path.exists())
            self.assertEqual(backup_path.read_text(encoding="utf-8"), "not json")
            self.assertIn("corrupt-20260101T000000.000000Z-abcd", backup_path.name)


class UniqueRunIdTests(unittest.TestCase):
    def test_avoids_collision_with_existing_run_history_file(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            runs_dir.mkdir()

            first_id = unique_run_id(runs_dir)
            (runs_dir / f"run_{first_id}.json").write_text("{}", encoding="utf-8")

            second_id = unique_run_id(runs_dir)

            self.assertNotEqual(first_id, second_id)
            self.assertFalse((runs_dir / f"run_{second_id}.json").exists())

    def test_generates_many_distinct_ids(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            runs_dir.mkdir()

            ids = set()
            for _ in range(50):
                run_id = unique_run_id(runs_dir)
                (runs_dir / f"run_{run_id}.json").write_text("{}", encoding="utf-8")
                ids.add(run_id)

            self.assertEqual(len(ids), 50)


class StageAndPublishRunTests(unittest.TestCase):
    def _payloads(self, run_id: str, metrics: dict):
        history_payload = build_run_history_payload(
            run_id=run_id,
            mode="full (no previous manifest)",
            manifest_status="missing",
            started_at=RUN_TS,
            generated_at=RUN_TS,
            exit_code=0,
            metrics=metrics,
            classification=_empty_classification(),
            excluded=[],
        )
        run_metadata_payload = build_run_metadata_payload(
            run_id=run_id,
            previous_run_id=None,
            mode="full (no previous manifest)",
            manifest_status="missing",
            started_at=RUN_TS,
            generated_at=RUN_TS,
            exit_code=0,
            metrics=metrics,
        )
        return history_payload, run_metadata_payload

    def test_publishes_all_three_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            indexes_dir = Path(tmp) / "08-Indexes" / "Metadata"
            entries = {"a.txt": _entry("a.txt")}
            metrics = _clean_metrics(discovered=1, eligible=1, processed=1, new=1, hashes_recomputed=1)
            history_payload, run_metadata_payload = self._payloads("run1", metrics)

            doc_path, run_meta_path, run_history_path = stage_and_publish_run(
                indexes_dir=indexes_dir,
                document_entries=entries,
                run_history_payload=history_payload,
                run_metadata_payload=run_metadata_payload,
                run_id="run1",
            )

            self.assertTrue(run_history_path.is_file())
            self.assertTrue(doc_path.is_file())
            self.assertTrue(run_meta_path.is_file())
            self.assertEqual(run_history_path.parent.name, RUN_HISTORY_SUBDIR)

            manifest_lines = doc_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(manifest_lines), 1)

            run_meta = json.loads(run_meta_path.read_text(encoding="utf-8"))
            self.assertEqual(run_meta["run_id"], "run1")

    def test_validation_failure_leaves_no_final_target_changed(self) -> None:
        with TemporaryDirectory() as tmp:
            indexes_dir = Path(tmp) / "08-Indexes" / "Metadata"
            indexes_dir.mkdir(parents=True)
            doc_path = indexes_dir / "document_manifest.jsonl"
            run_meta_path = indexes_dir / "manifest_run_metadata.json"
            doc_path.write_text("old-manifest-content\n", encoding="utf-8")
            run_meta_path.write_text('{"run_id": "old"}', encoding="utf-8")

            metrics = _clean_metrics()
            history_payload, _ = self._payloads("run2", metrics)
            # Deliberately broken: missing required top-level fields.
            broken_run_metadata_payload = {"schema_version": 2, "run_id": "run2"}

            with self.assertRaises(ValueError):
                stage_and_publish_run(
                    indexes_dir=indexes_dir,
                    document_entries={},
                    run_history_payload=history_payload,
                    run_metadata_payload=broken_run_metadata_payload,
                    run_id="run2",
                )

            self.assertEqual(doc_path.read_text(encoding="utf-8"), "old-manifest-content\n")
            self.assertEqual(json.loads(run_meta_path.read_text(encoding="utf-8"))["run_id"], "old")
            self.assertFalse((indexes_dir / RUN_HISTORY_SUBDIR / "run_run2.json").exists())

            leftover_temp_files = [
                p for p in indexes_dir.rglob("*") if p.is_file() and p.name.startswith(".")
            ]
            self.assertEqual(leftover_temp_files, [])

    def test_metrics_invariant_violation_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            indexes_dir = Path(tmp) / "08-Indexes" / "Metadata"
            metrics = _clean_metrics(discovered=5)  # inconsistent with eligible + excluded
            history_payload, run_metadata_payload = self._payloads("run3", metrics)

            with self.assertRaises(ValueError):
                stage_and_publish_run(
                    indexes_dir=indexes_dir,
                    document_entries={},
                    run_history_payload=history_payload,
                    run_metadata_payload=run_metadata_payload,
                    run_id="run3",
                )


if __name__ == "__main__":
    unittest.main()
