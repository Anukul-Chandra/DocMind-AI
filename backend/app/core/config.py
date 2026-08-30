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

    #: When True, FastAPI serves /docs, /redoc, and /openapi.json. Set to False
    #: in production to avoid exposing the API schema. Defaults to True so local
    #: development keeps the interactive docs.
    enable_docs: bool = True

    chunk_size: int = 1000
    chunk_overlap: int = 200

    #: Maximum allowed size in bytes for an uploaded document (default 50 MiB).
    max_upload_size_bytes: int = 50 * 1024 * 1024

    storage_dir: str = str(PROJECT_ROOT / "storage")
    faiss_index_path: str = str(PROJECT_ROOT / "storage" / "faiss" / "index.faiss")
    metadata_path: str = str(PROJECT_ROOT / "storage" / "metadata.json")
    documents_path: str = str(PROJECT_ROOT / "storage" / "documents.json")
    users_path: str = str(PROJECT_ROOT / "storage" / "users.json")
    conversations_path: str = str(PROJECT_ROOT / "storage" / "conversations.json")
    logs_dir: str = str(PROJECT_ROOT / "storage" / "logs")

    persistence_backend: str = "json"
    database_url: str = ""

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 604800

    #: Comma-separated list of browser origins allowed to call the API.
    #: Empty disallows all cross-origin browser requests (same-origin still works).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    #: Whether the CORS response advertises that credentials are supported.
    cors_allow_credentials: bool = True

    #: Master switch for the in-memory rate limiter.
    rate_limit_enabled: bool = True
    #: Maximum requests per client IP per minute outside /auth.
    rate_limit_per_minute: int = 300
    #: Maximum requests per client IP per minute on /auth endpoints.
    rate_limit_auth_per_minute: int = 60
    #: Trust X-Forwarded-For for the client IP when behind a reverse proxy.
    rate_limit_trust_proxy_headers: bool = False

    embedding_model: str = "all-MiniLM-L6-v2"

    #: Minimum cosine similarity between a chat query and the user's best
    #: matching indexed chunk for the query to be routed to document
    #: retrieval (RAG) instead of the general LLM path. Calibrated against
    #: real queries and a live corpus: document-anchored and implicit
    #: personal questions score >= ~0.20 while unrelated general chatter
    #: scores well below; topic-matching general questions (e.g. the corpus
    #: contains ML papers and the user asks about ML) intentionally route to
    #: RAG so the answer can be grounded in the user's own documents.
    rag_relevance_threshold: float = 0.20

    #: Semantic floor for self-referential (personal / self-attribute)
    #: questions. A question about the user's own documents ("my CV", "where
    #: did I study?") is routed to RAG when it carries first-person reference
    #: or a self-attribute and reaches this low cosine bar; the personal
    #: signal does most of the work, so the semantic requirement is weak.
    rag_personal_floor: float = 0.07

    #: Semantic bar for generic topical questions (no personal reference, no
    #: explicit document noun). A general question about a topic that merely
    #: exists in an uploaded paper must exceed this high cosine similarity to
    #: be routed to RAG; otherwise it stays GENERAL. Keeps e.g. "define
    #: machine learning" out of RAG when the corpus contains an ML paper.
    rag_topic_threshold: float = 0.45

    #: Semantic floor for questions that name a document noun ("paper",
    #: "document", "doc", "file"). Explicit document references can rescue
    #: low semantic scores when combined with positive owner-scoped BM25
    #: evidence.
    rag_docnoun_floor: float = 0.15

    llm_provider: str = ""
    default_model: str = "gpt-4o-mini"
    #: Verified present in the live Gemini catalog (models.list) and stable
    #: for general text use. gemini-2.0-flash was retired; gemini-3.6-flash is
    #: a newer/preview tier that some projects are denied access to.
    gemini_model: str = "gemini-3.6-flash"
    #: Verified against the live Groq model list and an end-to-end chat
    #: completion (returns clean text). llama-3.3-70b-versatile was removed by
    #: Groq; openai/gpt-oss-120b is available but emits empty content on this
    #: provider, so groq/compound-mini is used as the reliable fallback.
    groq_model: str = "groq/compound-mini"
    temperature: float = 0.0
    max_tokens: int = 1000
    timeout: int = 60

    #: Hard outer deadline (seconds) for the OPTIONAL CRAG query rewrite. The
    #: rewrite is a single best-effort LLM call that may internally rotate
    #: across providers/models; this ceiling guarantees provider rotation,
    #: retries, and transport timeouts can never block an interactive chat turn
    #: longer than this budget. On expiry the original contexts are preserved
    #: and corrective retrieval is skipped, so the user still gets the normal
    #: answer. Calibrated against baseline retrieval (~0.1s) and the typical
    #: sub-second-to-few-second latency of a healthy free-tier rewrite; 5s keeps
    #: a full CRAG turn responsive while tolerating normal variance plus a model
    #: rotation or two. It is the single outer safety boundary — no CRAG-level
    #: retry is added on top of the provider/OpenCode rotation beneath it.
    crag_rewrite_timeout_seconds: float = 2.0

    provider_priority: str = "agnes,opencode,openrouter,gemini,groq"

    openrouter_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""
    github_api_key: str = ""
    cerebras_api_key: str = ""
    sambanova_api_key: str = ""
    #: Agnes AI (OpenAI-compatible gateway). Base URL and default model are
    #: taken from the official Agnes AI documentation:
    #:   https://agnes-ai.com/doc/overview  (Base URL https://apihub.agnes-ai.com/v1)
    #: Verified chat models: agnes-2.5-flash, agnes-2.0-flash, agnes-1.5-flash.
    #: agnes-2.5-flash is the current flagship and is text + image-URL capable.
    agnes_api_key: str = ""
    agnes_base_url: str = "https://apihub.agnes-ai.com/v1"
    agnes_model: str = "agnes-2.5-flash"

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
        "conversations_path",
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

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse the comma-separated CORS_ORIGINS value into an origin list.

        Blank entries and surrounding whitespace are ignored so the value can
        be written naturally in a .env file.

        Returns:
            A list of origin strings, or an empty list when CORS is disabled.
        """
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
