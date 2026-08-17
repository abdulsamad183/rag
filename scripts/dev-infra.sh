#!/usr/bin/env bash
# Start Postgres + Redis for local (non-Docker) backend development.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up postgres redis -d
echo "Postgres :5432  Redis :6379"
echo "Next:  cd backend && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --reload"
