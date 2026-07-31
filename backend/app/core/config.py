from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application settings loaded from environment and .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "DocMind AI"
    APP_VERSION: str = "0.1.0"
    APP_DESCRIPTION: str = "An intelligent document analysis and management system powered by AI."

    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200

    STORAGE_DIR: str = "storage"
    FAISS_INDEX_PATH: str = "storage/faiss/index.faiss"
    METADATA_PATH: str = "storage/metadata.json"

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    TEMPERATURE: float = 0.0
    MAX_TOKENS: int = 1000


settings = Settings()

APP_NAME = settings.APP_NAME
APP_VERSION = settings.APP_VERSION
APP_DESCRIPTION = settings.APP_DESCRIPTION

CHUNK_SIZE = settings.CHUNK_SIZE
CHUNK_OVERLAP = settings.CHUNK_OVERLAP

STORAGE_DIR = settings.STORAGE_DIR
FAISS_INDEX_PATH = settings.FAISS_INDEX_PATH
METADATA_PATH = settings.METADATA_PATH

OPENAI_API_KEY = settings.OPENAI_API_KEY
OPENAI_MODEL = settings.OPENAI_MODEL
TEMPERATURE = settings.TEMPERATURE
MAX_TOKENS = settings.MAX_TOKENS
