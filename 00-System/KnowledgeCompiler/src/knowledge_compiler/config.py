from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILENAME = "aihub.json"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlatformConfig:
    root: Path
    name: str
    version: str
    execution_mode: str
    folders: dict[str, str]

    def folder_path(self, folder: str) -> Path:
        try:
            relative = self.folders[folder]
        except KeyError as exc:
            raise ConfigError(f"Unknown folder '{folder}' in {CONFIG_FILENAME}") from exc
        return self.root / relative


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / CONFIG_FILENAME).is_file():
            return candidate
    raise ConfigError(f"{CONFIG_FILENAME} not found in '{current}' or any parent directory")


def load_config(root: Path | None = None) -> PlatformConfig:
    root = find_repo_root(root)
    config_path = root / CONFIG_FILENAME

    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    try:
        platform = data["platform"]
        folders = data["folders"]
    except KeyError as exc:
        raise ConfigError(f"{CONFIG_FILENAME} missing required section: {exc}") from exc

    try:
        name = platform["name"]
        version = platform["version"]
        execution_mode = platform["execution_mode"]
    except KeyError as exc:
        raise ConfigError(f"{CONFIG_FILENAME} missing platform field: {exc}") from exc

    return PlatformConfig(
        root=root,
        name=name,
        version=version,
        execution_mode=execution_mode,
        folders=dict(folders),
    )
