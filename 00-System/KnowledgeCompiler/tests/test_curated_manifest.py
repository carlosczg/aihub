from __future__ import annotations

import json
import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from knowledge_compiler.curated_manifest import (
    RUN_HISTORY_SUBDIR,
    CuratedDocumentMetadata,
    CuratedManifestCorruptError,
    build_run_history_payload,
    build_run_metadata_payload,
    load_previous_curated_manifest,
    stage_and_publish_run,
    unique_run_id,
)
from knowledge_compiler.normalizer_diff import NormalizerClassificationResult

RUN_TS = "2026-01-01T00:00:00+00:00"


def _entry(relative_path: str) -> CuratedDocumentMetadata:
    return CuratedDocumentMetadata(
        document_id="00000000-0000-0000-0000-000000000000",
        relative_path=relative_path,
        knowledge_source="Manual",
        document_type="unknown",
        language="und",
        source_extension=".txt",
        source_sha256="0" * 64,
        converter_id="text_native",
        converter_version="1.0.0",
        output_relative_path=f"{relative_path}.md",
        output_sha256="1" * 64,
        first_seen_at=RUN_TS,
        last_converted_at=RUN_TS,
    )


def _clean_metrics(**overrides) -> dict:
    metrics = {
        "source_total": 0,
        "text_native": 0,
        "deferred": 0,
        "unsupported": 0,
        "converted_new": 0,
        "converted_stale": 0,
        "converted_stale_converter": 0,
        "unchanged": 0,
        "failed": 0,
        "orphaned": 0,
        "duration_seconds": 0.0,
    }
    metrics.update(overrides)
    return metrics


def _empty_classification() -> NormalizerClassificationResult:
    return NormalizerClassificationResult(curated_entries={})


class LoadPreviousCuratedManifestTests(unittest.TestCase):
    def test_missing_file_is_valid_empty_state(self) -> None:
        with TemporaryDirectory() as tmp:
            entries = load_previous_curated_manifest(Path(tmp) / "missing.jsonl")
            self.assertEqual(entries, {})

    def test_valid_manifest_round_trips(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_normalizer_manifest.jsonl"
            record = {
                "relative_path": "Manual/a.txt",
                "knowledge_source": "Manual",
                "source_extension": ".txt",
                "source_sha256": "0" * 64,
                "converter_id": "text_native",
                "converter_version": "1.0.0",
                "output_relative_path": "Manual/a.txt.md",
                "output_sha256": "1" * 64,
                "first_seen_at": RUN_TS,
                "last_converted_at": RUN_TS,
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            entries = load_previous_curated_manifest(path)

            self.assertEqual(entries["Manual/a.txt"].converter_version, "1.0.0")

    def test_corrupt_json_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_normalizer_manifest.jsonl"
            path.write_text("{not valid json\n", encoding="utf-8")

            with self.assertRaises(CuratedManifestCorruptError):
                load_previous_curated_manifest(path)

    def test_missing_required_field_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_normalizer_manifest.jsonl"
            path.write_text(json.dumps({"relative_path": "a.txt"}) + "\n", encoding="utf-8")

            with self.assertRaises(CuratedManifestCorruptError):
                load_previous_curated_manifest(path)

    def test_legacy_entry_without_document_id_is_backfilled_with_a_uuid4(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_normalizer_manifest.jsonl"
            legacy_record = {
                "relative_path": "Manual/a.txt",
                "knowledge_source": "Manual",
                "source_extension": ".txt",
                "source_sha256": "0" * 64,
                "converter_id": "text_native",
                "converter_version": "1.0.0",
                "output_relative_path": "Manual/a.txt.md",
                "output_sha256": "1" * 64,
                "first_seen_at": RUN_TS,
                "last_converted_at": RUN_TS,
            }
            path.write_text(json.dumps(legacy_record) + "\n", encoding="utf-8")

            entries = load_previous_curated_manifest(path)

            document_id = entries["Manual/a.txt"].document_id
            self.assertTrue(document_id)
            self.assertEqual(uuid.UUID(document_id).version, 4)

    def test_existing_document_id_is_preserved_on_load(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_normalizer_manifest.jsonl"
            record = {
                "document_id": "11111111-1111-4111-8111-111111111111",
                "relative_path": "Manual/a.txt",
                "knowledge_source": "Manual",
                "source_extension": ".txt",
                "source_sha256": "0" * 64,
                "converter_id": "text_native",
                "converter_version": "1.0.0",
                "output_relative_path": "Manual/a.txt.md",
                "output_sha256": "1" * 64,
                "first_seen_at": RUN_TS,
                "last_converted_at": RUN_TS,
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            entries = load_previous_curated_manifest(path)

            self.assertEqual(
                entries["Manual/a.txt"].document_id, "11111111-1111-4111-8111-111111111111"
            )

    def test_legacy_entry_without_document_type_is_backfilled_from_knowledge_source(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_normalizer_manifest.jsonl"
            legacy_record = {
                "relative_path": "OneDrive-Marketing/a.txt",
                "knowledge_source": "OneDrive-Marketing",
                "source_extension": ".txt",
                "source_sha256": "0" * 64,
                "converter_id": "text_native",
                "converter_version": "1.0.0",
                "output_relative_path": "OneDrive-Marketing/a.txt.md",
                "output_sha256": "1" * 64,
                "first_seen_at": RUN_TS,
                "last_converted_at": RUN_TS,
            }
            path.write_text(json.dumps(legacy_record) + "\n", encoding="utf-8")

            entries = load_previous_curated_manifest(path)

            self.assertEqual(entries["OneDrive-Marketing/a.txt"].document_type, "marketing")

    def test_legacy_entry_with_unmapped_knowledge_source_backfills_to_unknown(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_normalizer_manifest.jsonl"
            legacy_record = {
                "relative_path": "Manual/a.txt",
                "knowledge_source": "Manual",
                "source_extension": ".txt",
                "source_sha256": "0" * 64,
                "converter_id": "text_native",
                "converter_version": "1.0.0",
                "output_relative_path": "Manual/a.txt.md",
                "output_sha256": "1" * 64,
                "first_seen_at": RUN_TS,
                "last_converted_at": RUN_TS,
            }
            path.write_text(json.dumps(legacy_record) + "\n", encoding="utf-8")

            entries = load_previous_curated_manifest(path)

            self.assertEqual(entries["Manual/a.txt"].document_type, "unknown")

    def test_existing_document_type_is_preserved_on_load(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_normalizer_manifest.jsonl"
            record = {
                "document_type": "proposal",
                "relative_path": "OneDrive-Marketing/a.txt",
                "knowledge_source": "OneDrive-Marketing",
                "source_extension": ".txt",
                "source_sha256": "0" * 64,
                "converter_id": "text_native",
                "converter_version": "1.0.0",
                "output_relative_path": "OneDrive-Marketing/a.txt.md",
                "output_sha256": "1" * 64,
                "first_seen_at": RUN_TS,
                "last_converted_at": RUN_TS,
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            entries = load_previous_curated_manifest(path)

            # A stored (even if inconsistent with the current mapping)
            # value is preserved, not silently overwritten -- backfill only
            # applies when the field is absent.
            self.assertEqual(entries["OneDrive-Marketing/a.txt"].document_type, "proposal")

    def test_legacy_entry_without_language_is_backfilled_with_und(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_normalizer_manifest.jsonl"
            legacy_record = {
                "relative_path": "Manual/a.txt",
                "knowledge_source": "Manual",
                "source_extension": ".txt",
                "source_sha256": "0" * 64,
                "converter_id": "text_native",
                "converter_version": "1.0.0",
                "output_relative_path": "Manual/a.txt.md",
                "output_sha256": "1" * 64,
                "first_seen_at": RUN_TS,
                "last_converted_at": RUN_TS,
            }
            path.write_text(json.dumps(legacy_record) + "\n", encoding="utf-8")

            entries = load_previous_curated_manifest(path)

            self.assertEqual(entries["Manual/a.txt"].language, "und")

    def test_existing_language_is_preserved_on_load(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_normalizer_manifest.jsonl"
            record = {
                "language": "es",
                "relative_path": "Manual/a.txt",
                "knowledge_source": "Manual",
                "source_extension": ".txt",
                "source_sha256": "0" * 64,
                "converter_id": "text_native",
                "converter_version": "1.0.0",
                "output_relative_path": "Manual/a.txt.md",
                "output_sha256": "1" * 64,
                "first_seen_at": RUN_TS,
                "last_converted_at": RUN_TS,
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            entries = load_previous_curated_manifest(path)

            self.assertEqual(entries["Manual/a.txt"].language, "es")

    def test_duplicate_relative_path_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_normalizer_manifest.jsonl"
            record = {
                "relative_path": "Manual/a.txt",
                "knowledge_source": "Manual",
                "source_extension": ".txt",
                "source_sha256": "0" * 64,
                "converter_id": "text_native",
                "converter_version": "1.0.0",
                "output_relative_path": "Manual/a.txt.md",
                "output_sha256": "1" * 64,
                "first_seen_at": RUN_TS,
                "last_converted_at": RUN_TS,
            }
            line = json.dumps(record)
            path.write_text(line + "\n" + line + "\n", encoding="utf-8")

            with self.assertRaises(CuratedManifestCorruptError):
                load_previous_curated_manifest(path)


class UniqueRunIdReuseTests(unittest.TestCase):
    def test_curated_layer_reuses_manifest_unique_run_id(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            runs_dir.mkdir()
            first = unique_run_id(runs_dir)
            (runs_dir / f"run_{first}.json").write_text("{}", encoding="utf-8")
            second = unique_run_id(runs_dir)
            self.assertNotEqual(first, second)


class StageAndPublishRunTests(unittest.TestCase):
    def _payloads(self, run_id: str, metrics: dict):
        history_payload = build_run_history_payload(
            run_id=run_id,
            mode="initial",
            manifest_status="missing",
            started_at=RUN_TS,
            generated_at=RUN_TS,
            exit_code=0,
            metrics=metrics,
            classification=_empty_classification(),
        )
        run_metadata_payload = build_run_metadata_payload(
            run_id=run_id,
            previous_run_id=None,
            mode="initial",
            manifest_status="missing",
            started_at=RUN_TS,
            generated_at=RUN_TS,
            exit_code=0,
            metrics=metrics,
            classification=_empty_classification(),
        )
        return history_payload, run_metadata_payload

    def test_publishes_all_three_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            curated_metadata_dir = Path(tmp) / "02-Curated" / "Metadata"
            entries = {"a.txt": _entry("a.txt")}
            metrics = _clean_metrics(
                source_total=1, text_native=1, converted_new=1
            )
            history_payload, run_metadata_payload = self._payloads("run1", metrics)

            manifest_path, run_meta_path, run_history_path = stage_and_publish_run(
                curated_metadata_dir=curated_metadata_dir,
                document_entries=entries,
                run_history_payload=history_payload,
                run_metadata_payload=run_metadata_payload,
                run_id="run1",
            )

            self.assertTrue(run_history_path.is_file())
            self.assertTrue(manifest_path.is_file())
            self.assertTrue(run_meta_path.is_file())
            self.assertEqual(run_history_path.parent.name, RUN_HISTORY_SUBDIR)

            lines = manifest_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)

    def test_validation_failure_leaves_no_final_target_changed(self) -> None:
        with TemporaryDirectory() as tmp:
            curated_metadata_dir = Path(tmp) / "02-Curated" / "Metadata"
            curated_metadata_dir.mkdir(parents=True)
            manifest_path = curated_metadata_dir / "document_normalizer_manifest.jsonl"
            run_meta_path = curated_metadata_dir / "normalizer_run_metadata.json"
            manifest_path.write_text("old-content\n", encoding="utf-8")
            run_meta_path.write_text('{"run_id": "old"}', encoding="utf-8")

            metrics = _clean_metrics()
            history_payload, _ = self._payloads("run2", metrics)
            broken_run_metadata_payload = {"schema_version": 1, "run_id": "run2"}

            with self.assertRaises(ValueError):
                stage_and_publish_run(
                    curated_metadata_dir=curated_metadata_dir,
                    document_entries={},
                    run_history_payload=history_payload,
                    run_metadata_payload=broken_run_metadata_payload,
                    run_id="run2",
                )

            self.assertEqual(manifest_path.read_text(encoding="utf-8"), "old-content\n")
            self.assertEqual(
                json.loads(run_meta_path.read_text(encoding="utf-8"))["run_id"], "old"
            )
            self.assertFalse((curated_metadata_dir / RUN_HISTORY_SUBDIR / "run_run2.json").exists())

            leftover_temp_files = [
                p for p in curated_metadata_dir.rglob("*") if p.is_file() and p.name.startswith(".")
            ]
            self.assertEqual(leftover_temp_files, [])

    def test_metrics_invariant_violation_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            curated_metadata_dir = Path(tmp) / "02-Curated" / "Metadata"
            metrics = _clean_metrics(source_total=5)  # inconsistent with the other buckets
            history_payload, run_metadata_payload = self._payloads("run3", metrics)

            with self.assertRaises(ValueError):
                stage_and_publish_run(
                    curated_metadata_dir=curated_metadata_dir,
                    document_entries={},
                    run_history_payload=history_payload,
                    run_metadata_payload=run_metadata_payload,
                    run_id="run3",
                )


if __name__ == "__main__":
    unittest.main()
