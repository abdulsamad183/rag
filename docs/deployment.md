# Deployment

## Docker Compose (development / single host)

```bash
cp .env.example .env
docker compose up --build
```

Services: `frontend` (nginx :3000), `backend` (:8000), `worker`, `postgres` (pgvector), `redis`.

Ollama should run on the host (or another compose file) and `OLLAMA_BASE_URL` must be reachable from the backend container (`http://host.docker.internal:11434` on Docker Desktop).

## Migrations

The backend container runs `alembic upgrade head` on start. For existing volumes:

```bash
docker compose exec backend uv run alembic upgrade head
```

## Configuration

Pass secrets via environment or an orchestrator secret store. Do not bake keys into images. `SECRET_KEY` must be rotated in any shared environment.

## Production notes

- Put a real TLS terminator in front of nginx
- Restrict CORS to the actual origin
- Use managed Postgres with pgvector; size the connection pool (`DB_POOL_SIZE`)
- Run multiple worker replicas for ingestion/eval
- Set `JSON_LOGS=true` and ship stdout to your collector
- `TraceRecorder` is OpenTelemetry-shaped (named spans + attributes); wire an exporter when you need distributed tracing
- Replace the default user with real auth before exposing the API
- Object storage: implement `BlobStore` for S3/MinIO rather than the local disk backend

## Health

- `GET /api/v1/health` — process up
- `GET /api/v1/ready` — database, redis, provider configuration, storage (no secret values)

Load balancers should use `/health` for liveness and `/ready` for readiness.
