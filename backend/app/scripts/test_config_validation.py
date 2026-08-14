"""Focused configuration-validation and .env.example safety tests.

Verifies that ``Settings`` rejects a missing/empty ``JWT_SECRET``, only
requires ``DATABASE_URL`` when the ``postgres`` backend is selected, and that
``.env.example`` contains none of the real secret values stored in ``.env``.

The real ``.env`` file is never modified and real values are never printed.

Usage (from backend/):
    python -m app.scripts.test_config_validation

Exit status is non-zero if any check fails.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

# Module-level `settings = Settings()` in app.core.config requires a JWT_SECRET;
# provide one before importing the app so this test module itself loads.
os.environ.setdefault("JWT_SECRET", "test-secret-for-config-validation")

from pydantic import ValidationError

from app.core.config import PROJECT_ROOT, Settings  # noqa: E402

BACKEND_DIR = PROJECT_ROOT

#: Keys whose values are secrets and must never be reproduced in .env.example.
SECRET_KEYS = {
    "JWT_SECRET",
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "GITHUB_API_KEY",
    "CEREBRAS_API_KEY",
    "SAMBANOVA_API_KEY",
    "DATABASE_URL",
}


def _settings(**env_overrides):
    """Build a fresh Settings instance from environment overrides only.

    ``_env_file=None`` keeps the test hermetic: the real ``.env`` is not read,
    so environment variables fully control the configuration under test.
    """
    with mock.patch.dict(os.environ, env_overrides, clear=False):
        return Settings(_env_file=None)


def _load_env(path: Path) -> dict:
    """Parse a simple KEY=VALUE env file (ignores comments and blanks)."""
    pairs = {}
    if not path.exists():
        return pairs
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        pairs[key.strip()] = value.strip().strip('"').strip("'")
    return pairs


class ConfigValidationTests(unittest.TestCase):
    def test_jwt_secret_missing_fails(self):
        with self.assertRaises(ValidationError):
            _settings(JWT_SECRET="", PERSISTENCE_BACKEND="json", DATABASE_URL="")

    def test_jwt_secret_present_valid(self):
        config = _settings(
            JWT_SECRET="a-valid-secret", PERSISTENCE_BACKEND="json", DATABASE_URL=""
        )
        self.assertEqual(config.jwt_secret, "a-valid-secret")

    def test_json_backend_without_database_url_valid(self):
        config = _settings(
            JWT_SECRET="a-valid-secret", PERSISTENCE_BACKEND="json", DATABASE_URL=""
        )
        self.assertEqual(config.persistence_backend, "json")
        self.assertEqual(config.database_url, "")

    def test_postgres_without_database_url_fails(self):
        with self.assertRaises(ValidationError):
            _settings(
                JWT_SECRET="a-valid-secret",
                PERSISTENCE_BACKEND="postgres",
                DATABASE_URL="",
            )

    def test_postgres_with_database_url_valid(self):
        config = _settings(
            JWT_SECRET="a-valid-secret",
            PERSISTENCE_BACKEND="postgres",
            DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/docmind",
        )
        self.assertEqual(config.persistence_backend, "postgres")
        self.assertEqual(config.database_url, "postgresql+psycopg://user:pass@localhost:5432/docmind")

    def test_env_example_contains_no_real_secrets(self):
        example_path = BACKEND_DIR / ".env.example"
        env_path = BACKEND_DIR / ".env"
        self.assertTrue(example_path.exists(), ".env.example must exist")
        self.assertTrue(env_path.exists(), "real .env must exist for comparison")
        real_secret_values = {
            value
            for key, value in _load_env(env_path).items()
            if key in SECRET_KEYS and value
        }
        example_text = example_path.read_text(encoding="utf-8")
        for value in real_secret_values:
            self.assertNotIn(value, example_text)


def main() -> int:
    print("=" * 60)
    print("Configuration Validation Test")
    print("=" * 60)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ConfigValidationTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("=" * 60)
    print(
        f"Configuration Validation Test "
        f"{'PASSED' if result.wasSuccessful() else 'FAILED'}"
    )
    print("=" * 60)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())