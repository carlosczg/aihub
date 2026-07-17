from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from knowledge_compiler.io_utils import stage_text


class StageTextTests(unittest.TestCase):
    def test_stage_then_publish_replaces_target(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "out.txt"
            target.write_text("old", encoding="utf-8")

            staged = stage_text(target, "new", validator=lambda content: None)

            self.assertTrue(staged.tmp_path.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "old")

            staged.publish()

            self.assertEqual(target.read_text(encoding="utf-8"), "new")
            self.assertFalse(staged.tmp_path.exists())

    def test_validation_failure_leaves_target_untouched_and_removes_temp_file(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "out.txt"
            target.write_text("old", encoding="utf-8")

            def failing_validator(content: str) -> None:
                raise ValueError("invalid content")

            with self.assertRaises(ValueError):
                stage_text(target, "new", validator=failing_validator)

            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            leftover = [p for p in Path(tmp).iterdir() if p.name != "out.txt"]
            self.assertEqual(leftover, [])

    def test_stage_without_existing_target_creates_parent_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "out.txt"

            staged = stage_text(target, "content", validator=lambda content: None)
            staged.publish()

            self.assertEqual(target.read_text(encoding="utf-8"), "content")

    def test_discard_removes_staged_temp_file_without_publishing(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "out.txt"

            staged = stage_text(target, "content", validator=lambda content: None)
            staged.discard()

            self.assertFalse(staged.tmp_path.exists())
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
