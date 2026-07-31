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


settings = Settings()
