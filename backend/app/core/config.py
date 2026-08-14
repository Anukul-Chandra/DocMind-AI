from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root is the directory that contains the storage/ folder (i.e. backend/).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Centralized application settings loaded from environment and .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "DocMind AI"
    app_version: str = "0.1.0"
    app_description: str = "An intelligent document analysis and management system powered by AI."

    chunk_size: int = 1000
    chunk_overlap: int = 200

    #: Maximum allowed size in bytes for an uploaded document (default 50 MiB).
    max_upload_size_bytes: int = 50 * 1024 * 1024

    storage_dir: str = str(PROJECT_ROOT / "storage")
    faiss_index_path: str = str(PROJECT_ROOT / "storage" / "faiss" / "index.faiss")
    metadata_path: str = str(PROJECT_ROOT / "storage" / "metadata.json")
    documents_path: str = str(PROJECT_ROOT / "storage" / "documents.json")
    users_path: str = str(PROJECT_ROOT / "storage" / "users.json")
    logs_dir: str = str(PROJECT_ROOT / "storage" / "logs")

    persistence_backend: str = "json"
    database_url: str = ""

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 604800

    embedding_model: str = "all-MiniLM-L6-v2"

    llm_provider: str = ""
    default_model: str = "gpt-4o-mini"
    gemini_model: str = "gemini-2.0-flash"
    groq_model: str = "llama-3.3-70b-versatile"
    temperature: float = 0.0
    max_tokens: int = 1000
    timeout: int = 60

    provider_priority: str = "openrouter,gemini,groq"

    openrouter_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""
    github_api_key: str = ""
    cerebras_api_key: str = ""
    sambanova_api_key: str = ""

    @model_validator(mode="after")
    def _resolve_storage_paths(self) -> "Settings":
        """Anchor any relative storage paths to the project root.

        Relative paths (defaults or .env overrides) are resolved against the
        project root so persistence is machine-independent and never depends
        on the process working directory.

        Returns:
            The settings instance with normalized storage paths.
        """
        for field in (
        "storage_dir",
        "faiss_index_path",
        "metadata_path",
        "documents_path",
        "users_path",
        "logs_dir",
    ):
            path = Path(getattr(self, field))
            if not path.is_absolute():
                setattr(self, field, str((PROJECT_ROOT / path).resolve()))
        return self

    @model_validator(mode="after")
    def _validate_required_settings(self) -> "Settings":
        """Enforce required configuration at startup.

        Authentication always needs a signing secret: refuse to start with an
        empty ``JWT_SECRET`` instead of failing obscurely on the first request.

        ``DATABASE_URL`` is only required for the ``postgres`` persistence
        backend; the default JSON backend runs without it.
        """
        if not self.jwt_secret.strip():
            raise ValueError(
                "JWT_SECRET is required but was not provided. Set JWT_SECRET "
                "in the environment or in .env (see .env.example)."
            )
        if (
            self.persistence_backend.strip().lower() == "postgres"
            and not self.database_url.strip()
        ):
            raise ValueError(
                "DATABASE_URL is required when PERSISTENCE_BACKEND == 'postgres'."
            )
        return self


settings = Settings()
