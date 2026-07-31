from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application settings loaded from environment and .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "DocMind AI"
    app_version: str = "0.1.0"
    app_description: str = "An intelligent document analysis and management system powered by AI."

    chunk_size: int = 1000
    chunk_overlap: int = 200

    storage_dir: str = "storage"
    faiss_index_path: str = "storage/faiss/index.faiss"
    metadata_path: str = "storage/metadata.json"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    temperature: float = 0.0
    max_tokens: int = 1000


settings = Settings()
