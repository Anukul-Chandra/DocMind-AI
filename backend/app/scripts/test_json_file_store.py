"""JsonFileStore atomic-write regression test.

Verifies the crash-safety fix for :class:`JsonFileStore.save`:

- data round-trips exactly as before,
- the pretty-printed formatting is preserved,
- parent directories are still created on demand,
- a failed write raises and leaves the original target intact with no
  leftover temporary files.

Usage (from backend/):
    python -m app.scripts.test_json_file_store

Exit status is non-zero if any check fails.
"""

import sys
import tempfile
from pathlib import Path

from app.services.storage.json_file_store import JsonFileStore


def main() -> int:
    """Run the JsonFileStore atomic-write regression test."""
    print("=" * 60)
    print("JsonFileStore Atomic Write Test")
    print("=" * 60)

    check_results: list[bool] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}" + (f" - {detail}" if detail else ""))
        check_results.append(passed)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Round trip: data saved is exactly what is loaded back.
        path = root / "nested" / "dir" / "store.json"
        data = {"a": 1, "b": [1, 2, 3], "c": {"d": "text"}}
        JsonFileStore.save(path, data)
        check("parent directories are created on demand", path.exists())
        check("saved data round-trips on load", JsonFileStore.load(path, {}) == data)
        check("default used when file is missing", JsonFileStore.load(root / "nope.json", 42) == 42)

        # Formatting preserved: pretty-printed with two-space indentation.
        raw = path.read_text(encoding="utf-8")
        check(
            "pretty-printed formatting preserved",
            raw.startswith("{\n  \"a\": 1,"),
            raw.splitlines()[0:2],
        )

        # A failed write raises and leaves the original target untouched, and
        # no temporary files are left behind.
        original = {"k": "original"}
        target = root / "store.json"
        JsonFileStore.save(target, original)
        before = sorted(p.name for p in root.iterdir())
        try:
            JsonFileStore.save(target, {"bad": set([1])})
            check("non-serializable write raises", False, "no error raised")
        except TypeError:
            check("non-serializable write raises", True)
        check(
            "original target is not partially written",
            JsonFileStore.load(target, None) == original,
        )
        after = sorted(p.name for p in root.iterdir())
        check(
            "no leftover temporary files",
            after == before,
            f"{after} vs {before}",
        )

    print("\n" + "=" * 60)
    all_passed = all(check_results)
    print("JsonFileStore Test " + ("PASSED" if all_passed else "FAILED"))
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
