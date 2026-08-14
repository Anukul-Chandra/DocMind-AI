"""Shared JSON file persistence for the application's data stores."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class JsonFileStore:
    """Shared JSON persistence used by the application's data stores.

    Consolidates parent-directory creation, JSON reading, and pretty-printed
    JSON writing so each store only owns its domain logic. Writes are atomic:
    content is staged in a temporary file in the same directory and then moved
    into place with :func:`os.replace`, so a crash or failed write never leaves
    a partially written target file.
    """

    @staticmethod
    def ensure_parent(path: str | Path) -> Path:
        """Create the parent directory of a path when it is missing.

        Args:
            path: The file path whose parent directory should exist.

        Returns:
            The normalized path with its parent directory created.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def save(path: str | Path, data: Any) -> None:
        """Persist data to a file as pretty-printed JSON, atomically.

        The data is first written to a temporary file in the same directory,
        flushed to disk, and then atomically moved over the target with
        :func:`os.replace`. If writing fails, the temporary file is removed
        and the existing target (if any) is left untouched.

        Args:
            path: The file path to write to.
            data: The JSON-serializable data to persist.
        """
        path = JsonFileStore.ensure_parent(path)
        fd, tmp_name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    @staticmethod
    def load(path: str | Path, default: Any) -> Any:
        """Read JSON data from a file, falling back to a default when missing.

        Args:
            path: The file path to read from.
            default: The value to return when the file does not exist.

        Returns:
            The parsed data, or ``default`` when the file is absent.
        """
        path = Path(path)
        if not path.exists():
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
