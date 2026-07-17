from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable


class StagedArtifact:
    """A validated temporary file waiting to replace `final_path`.

    Staging (write + validate) and publishing (os.replace) are separate
    steps so a caller can stage several artifacts, confirm every one of
    them is valid, and only then publish any of them.
    """

    def __init__(self, tmp_path: Path, final_path: Path):
        self.tmp_path = tmp_path
        self.final_path = final_path

    def publish(self) -> Path:
        os.replace(self.tmp_path, self.final_path)
        return self.final_path

    def discard(self) -> None:
        self.tmp_path.unlink(missing_ok=True)


def stage_text(
    final_path: Path,
    content: str,
    validator: Callable[[str], None] | None = None,
) -> StagedArtifact:
    """Write `content` to a temp file next to `final_path` and validate it.

    The temp file lives in the same directory as `final_path` so the later
    `os.replace()` is an atomic rename on the same filesystem. On validation
    failure the temp file is removed and the exception propagates; `final_path`
    is never touched by this function.
    """
    final_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=final_path.parent, prefix=f".{final_path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        if validator is not None:
            validator(tmp_path.read_text(encoding="utf-8"))
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return StagedArtifact(tmp_path=tmp_path, final_path=final_path)
