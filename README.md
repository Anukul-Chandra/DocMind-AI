<div align="center">

# DocMind AI

### *Chat with your documents. Grounded. Hybrid. Multi-user.*

**A full-stack Retrieval-Augmented Generation (RAG) platform** built with FastAPI + React 19

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.139-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-Strict-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![FAISS](https://img.shields.io/badge/FAISS-Vector%20Search-1C3C5C?style=for-the-badge&logo=meta&logoColor=white)](https://faiss.ai)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![License](https://img.shields.io/badge/License-MIT-10B981?style=for-the-badge&logo=opensourceinitiative&logoColor=white)](LICENSE)

</div>

---

Upload PDFs, and DocMind indexes them into a FAISS vector store; ask questions in plain language and get answers grounded strictly in your corpus — with a relevance gate that knows when *not* to retrieve and defers to the LLM's general knowledge instead.

```text
PDF ──▶ extract ──▶ clean ──▶ chunk ──▶ embed ──▶ FAISS
                                                    │
question ──▶ relevance gate ──▶ hybrid retrieval ──▶ grounded prompt ──▶ LLM failover chain ──▶ answer
```

---

## Highlights

- **Hybrid retrieval** — semantic (FAISS `IndexFlatL2`) fused with Okapi BM25 via Reciprocal Rank Fusion (k=60), deduplicated on `(workspace, document, chunk)`, then reranked through a pluggable reranker protocol.
- **Relevance-gated query routing** — every question is scored against the owner's corpus (semantic cosine + lexical BM25 evidence). Document-anchored questions route to RAG; general chatter goes straight to the LLM. Calibrated thresholds (`RAG_RELEVANCE_THRESHOLD`, personal/topic/doc-noun floors) keep "define machine learning" out of your paper corpus while "what does *my* paper claim?" routes in.
- **Multi-provider LLM failover** — OpenRouter → Gemini → Groq, with round-robin model pooling, per-model rotation, timeout budgets, and free-tier model discovery at startup. One provider dying never fails a request.
- **Real authentication** — JWT access/refresh pairs (HS256), scrypt password hashing with self-describing parameters and a DoS guard, uniform error responses that never leak *why* auth failed.
- **Strict multi-user isolation** — every retrieval, chat, list, and delete is owner-scoped at the service layer. Users physically cannot read each other's chunks.
- **Transactionally safe uploads** — pre-upload state snapshots, atomic file writes (`fsync` + `os.replace`), and full compensation/rollback (FAISS index, metadata, physical file) if any step of indexing fails.
- **Bounded uploads** — streamed reads enforce a hard size cap (default 50 MiB) without buffering the payload first.
- **Swappable persistence** — JSON file store by default (zero infra); PostgreSQL 17 behind the same repository interfaces via SQLAlchemy 2 + Alembic migrations.
- **Structured intelligence** — automatic document classification, LLM-driven structured field extraction, OCR fallback for scanned PDFs.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python · FastAPI · Pydantic v2 · Uvicorn |
| Frontend | React 19 · Vite · TypeScript (strict) · Tailwind CSS v4 |
| UI System | Radix-based components · lucide-react · react-dropzone |
| State/Data | TanStack Query v5 · Axios (auto token refresh) · react-hook-form + Zod |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`, 384-dim) |
| Vector search | FAISS (`IndexFlatL2`) |
| Keyword search | Okapi BM25 + RRF fusion |
| PDF pipeline | PyMuPDF · langchain-text-splitters · OCR fallback |
| LLMs | OpenRouter · Google Gemini · Groq (httpx streaming, failover) |
| Persistence | JSON files (default) · PostgreSQL 17 + SQLAlchemy 2 + psycopg3 |
| Migrations | Alembic |
| Infra | Docker Compose |

## Architecture

Clean, dependency-inverted layers — high-level services depend only on abstractions (`Retriever`, `DocumentRepository`, `BaseProvider`) injected via a composition root:

```
frontend/ (React SPA)
   │  axios + JWT bearer, single-flight refresh
   ▼
backend/app/api/            HTTP layer — routes, DI, error envelopes, rate limiting, CORS
   ▼
backend/app/services/       Orchestration & domain
   ├── chat/                Query router (relevance gate) + RAG orchestration
   ├── document/            Indexing pipeline, classification, extraction, state snapshots
   ├── retrieval/           BM25 · Hybrid (RRF) · Reranker protocol
   ├── llm/                 Provider manager, failover chain, model pool, prompt builder
   ├── vectorstore/         Semantic retriever, metadata store, workspaces
   └── auth/                AuthService · JWTService · scrypt PasswordService
   ▼
backend/app/repositories/   DocumentRepository · UserRepository · LogRepository
   ├── json/                Zero-infra default
   └── postgres/            SQLAlchemy implementations behind identical interfaces
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- A `.env` for the backend (see [`backend/.env.example`](backend/.env.example)) — at minimum a `JWT_SECRET` and one provider API key

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then fill in JWT_SECRET + an LLM API key
uvicorn app.main:app --reload
```

The first run downloads the embedding model (~90 MB). API docs land at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

### Optional: PostgreSQL backend

```bash
docker compose up -d        # starts Postgres 17 with health checks
```

Then set in `backend/.env`:

```env
PERSISTENCE_BACKEND=postgres
DATABASE_URL=postgresql+psycopg://docmind:docmind@localhost:5432/docmind
```

and apply migrations with Alembic (`alembic upgrade head`). With the default `PERSISTENCE_BACKEND=json`, no database is needed at all.

## API Reference

All responses use a standard envelope: `{ success, data }` or `{ success, error: { code, message } }`.

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | — | Liveness/health probe |
| POST | `/auth/register` | — | Create an account (scrypt-hashed credentials) |
| POST | `/auth/login` | — | Issue access + refresh token pair |
| POST | `/auth/refresh` | — | Redeem a refresh token for a new pair |
| POST | `/documents/upload` | Bearer | Upload + fully index a PDF (size-bounded, rollback-safe) |
| GET | `/documents` | Bearer | List the caller's documents |
| GET | `/documents/{id}` | Bearer | Fetch one owned document |
| DELETE | `/documents/{id}` | Bearer | Soft-delete an owned document |
| POST | `/retrieve` | Bearer | Raw hybrid retrieval, owner-scoped |
| POST | `/chat/` | Bearer | RAG answer with automatic relevance gating |

## Configuration

Full reference in [`backend/.env.example`](backend/.env.example). Key knobs:

| Variable | Default | Notes |
|---|---|---|
| `JWT_SECRET` | — (**required**) | Long random string; server refuses to start without it |
| `PERSISTENCE_BACKEND` | `json` | `json` or `postgres` |
| `PROVIDER_PRIORITY` | `openrouter,gemini,groq` | Failover order |
| `RATE_LIMIT_PER_MINUTE` / `_AUTH_` | 300 / 60 | Per-IP fixed windows; stricter on auth endpoints |
| `CORS_ORIGINS` | Vite dev origins | Comma-separated allowlist |
| `MAX_UPLOAD_SIZE_BYTES` | 50 MiB | Hard streaming cap |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 1000 / 200 | Recursive character splitting |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Any sentence-transformers model |

## Engineering Notes & Known Trade-offs

Written honestly — these are conscious decisions, not oversights:

- **Soft deletion**: deleting a document removes its registry entry (and filters it from all retrieval immediately), but its vectors remain in FAISS until compaction. Cheap and safe; reclamation is future work.
- **Process-local state**: the vector store, metadata cache, and rate limiter are in-memory singletons. This matches the single-process deployment target; horizontal scaling wants Redis-backed limiting and shared storage first.
- **CPU-bound pipeline stages** (embedding, PDF parsing) currently run inline in request handlers; offloading to a worker pool is on the roadmap for high-concurrency deployments.
- **Refresh tokens are stateless** — revocation-on-logout requires a token denylist, planned alongside session management features.

## Roadmap

- [ ] Streaming chat responses (SSE end-to-end)
- [ ] Vector compaction on document deletion
- [ ] Workspace management UI (multi-workspace per user)
- [ ] External rerankers (Cohere / Jina / BGE) behind the existing protocol
- [ ] Background indexing workers
- [ ] CI pipeline (lint + typecheck + test suites)

## License

[MIT](LICENSE)
