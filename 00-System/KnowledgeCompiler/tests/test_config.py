from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from knowledge_compiler.config import ConfigError, find_repo_root, load_config


class FindRepoRootTests(unittest.TestCase):
    def test_finds_root_from_nested_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "aihub.json").write_text("{}", encoding="utf-8")
            nested = root / "00-System" / "KnowledgeCompiler"
            nested.mkdir(parents=True)

            self.assertEqual(find_repo_root(nested), root)

    def test_raises_when_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                find_repo_root(Path(tmp))


class LoadConfigTests(unittest.TestCase):
    def test_loads_platform_and_folders(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config_data = {
                "platform": {
                    "name": "AI Hub",
                    "version": "0.1.0",
                    "execution_mode": "local",
                },
                "storage": {"type": "local-filesystem", "root": "."},
                "folders": {"ingestion": "01-Ingestion", "indexes": "08-Indexes"},
            }
            (root / "aihub.json").write_text(json.dumps(config_data), encoding="utf-8")

            config = load_config(root)

            self.assertEqual(config.name, "AI Hub")
            self.assertEqual(config.folder_path("ingestion"), root / "01-Ingestion")

    def test_missing_platform_field_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "aihub.json").write_text(json.dumps({"folders": {}}), encoding="utf-8")

            with self.assertRaises(ConfigError):
                load_config(root)


if __name__ == "__main__":
    unittest.main()
