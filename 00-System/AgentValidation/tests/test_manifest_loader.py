from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_validation.manifest_loader import ManifestEntry, ManifestError, load_manifest

FIXTURE_RECORD = {
    "converter_id": "text_native",
    "converter_version": "1.1.0",
    "document_id": "11111111-1111-1111-1111-111111111111",
    "document_type": "proposal",
    "first_seen_at": "2026-07-20T03:09:09.550725+00:00",
    "knowledge_source": "OneDrive-Proposals",
    "language": "es",
    "last_converted_at": "2026-07-27T19:42:02.584090+00:00",
    "output_relative_path": "OneDrive-Proposals/Caso_Financiera.py.md",
    "output_sha256": "a" * 64,
    "relative_path": "OneDrive-Proposals/Caso_Financiera.py",
    "source_extension": ".py",
    "source_sha256": "b" * 64,
}


def _write_manifest(path: Path, records: list[dict]) -> None:
    lines = [json.dumps(record) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


class LoadManifestTests(unittest.TestCase):
    def test_loads_valid_manifest_with_documented_schema(self) -> None:
        with TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.jsonl"
            _write_manifest(manifest_path, [FIXTURE_RECORD])

            entries = load_manifest(manifest_path)

            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertIsInstance(entry, ManifestEntry)
            self.assertEqual(entry.document_id, FIXTURE_RECORD["document_id"])
            self.assertEqual(entry.relative_path, FIXTURE_RECORD["relative_path"])
            self.assertEqual(entry.source_extension, ".py")

    def test_loads_multiple_entries_in_file_order(self) -> None:
        second_record = dict(FIXTURE_RECORD)
        second_record["document_id"] = "22222222-2222-2222-2222-222222222222"
        second_record["relative_path"] = "OneDrive-Portfolio/Other.txt"

        with TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.jsonl"
            _write_manifest(manifest_path, [FIXTURE_RECORD, second_record])

            entries = load_manifest(manifest_path)

            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0].document_id, FIXTURE_RECORD["document_id"])
            self.assertEqual(entries[1].document_id, second_record["document_id"])

    def test_skips_blank_lines(self) -> None:
        with TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.jsonl"
            manifest_path.write_text(
                json.dumps(FIXTURE_RECORD) + "\n\n\n", encoding="utf-8"
            )

            entries = load_manifest(manifest_path)

            self.assertEqual(len(entries), 1)

    def test_missing_manifest_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            missing_path = Path(tmp) / "does_not_exist.jsonl"

            with self.assertRaises(ManifestError):
                load_manifest(missing_path)

    def test_invalid_json_line_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.jsonl"
            manifest_path.write_text("{not valid json\n", encoding="utf-8")

            with self.assertRaises(ManifestError):
                load_manifest(manifest_path)

    def test_missing_required_field_raises(self) -> None:
        incomplete_record = dict(FIXTURE_RECORD)
        del incomplete_record["language"]

        with TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.jsonl"
            _write_manifest(manifest_path, [incomplete_record])

            with self.assertRaises(ManifestError):
                load_manifest(manifest_path)

    def test_non_object_line_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.jsonl"
            manifest_path.write_text('["not", "an", "object"]\n', encoding="utf-8")

            with self.assertRaises(ManifestError):
                load_manifest(manifest_path)


if __name__ == "__main__":
    unittest.main()
