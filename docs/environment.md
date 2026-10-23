# Environment Variables Reference

All environment variables used by the platform are configured via `.env` (or environment injection in containerized deployments).

## Variable Schema

| Variable | Required | Default | Phase | Description |
| :--- | :---: | :--- | :---: | :--- |
| `APP_ENV` | **Yes** | `development` | Phase 0 | Runtime environment (`development`, `staging`, `production`) |
| `APP_NAME` | **Yes** | `RAG Platform` | Phase 0 | Platform application identifier |
| `APP_VERSION` | **Yes** | `0.1.0` | Phase 0 | Software release version |
| `API_V1_PREFIX` | No | `/api/v1` | Phase 0 | Base route prefix for API v1 |
| `DEBUG` | No | `false` | Phase 0 | Enables debug logging & reload |
| `PORT` | No | `8001` | Phase 0 | Backend listening port |
| `BACKEND_PORT` | No | `8001` | Phase 0 | Host mapped port for Docker backend |
| `FRONTEND_PORT` | No | `3001` | Phase 0 | Host mapped port for Docker frontend / dev server |
| `HOST` | No | `0.0.0.0` | Phase 0 | Backend listening host |
| `ORGANIZATION_NAME` | **Yes** | `Demo Organization` | Phase 0 | Client organization name displayed in UI |
| `BOT_NAME` | **Yes** | `AI Assistant` | Phase 0 | Name of the virtual assistant |
| `LOGO_URL` | No | `""` | Phase 0 | Optional external URL for branding logo |
| `PRIMARY_COLOR` | No | `#2563EB` | Phase 0 | Theme accent hex color code |
| `DATABASE_URL` | **Yes** | `postgresql+asyncpg://rag:rag@localhost:5432/rag` | Phase 0 | Async PostgreSQL connection string |
| `POSTGRES_USER` | **Yes** | `rag` | Phase 0 | PostgreSQL container user |
| `POSTGRES_PASSWORD` | **Yes** | `rag` | Phase 0 | PostgreSQL container password |
| `POSTGRES_DB` | **Yes** | `rag` | Phase 0 | PostgreSQL database name |
| `POSTGRES_PORT` | No | `5432` | Phase 0 | PostgreSQL mapped host port |
| `REDIS_URL` | **Yes** | `redis://localhost:6379/0` | Phase 0 | Redis connection string for cache/queue |
| `LLM_PROVIDER` | No | `""` | Phase 6 | LLM provider (e.g. `openai`, `gemini`, `ollama`) |
| `LLM_MODEL` | No | `""` | Phase 6 | Specific model name (e.g. `gpt-4o`, `gemini-1.5-pro`) |
| `OPENAI_API_KEY` | No | `""` | Phase 6 | OpenAI API secret key |
| `GEMINI_API_KEY` | No | `""` | Phase 6 | Google Gemini API secret key |
| `EMBEDDING_PROVIDER` | No | `""` | Phase 4 | Embedding model provider |
| `EMBEDDING_MODEL` | No | `""` | Phase 4 | Embedding model identifier |
| `STORAGE_PROVIDER` | No | `local` | Phase 3 | Document storage engine (`local`, `s3`, `gcs`) |
| `STORAGE_BUCKET` | No | `""` | Phase 3 | Cloud storage bucket name |
| `JWT_SECRET` | No | `""` | Phase 1 | Secret key for JWT signing |

---

## Security Guidelines

1. **Never commit `.env`**: `.gitignore` strictly rejects `.env` and `.env.*`.
2. **Template Only**: `.env.example` must contain only default non-sensitive values and blank secrets.
3. **Fail-Fast Validation**: Backend startup will fail validation immediately if required environment variables are absent.
