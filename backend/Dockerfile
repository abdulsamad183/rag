FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    STORAGE_DIR=/data/uploads

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
COPY backend/app ./app
RUN uv sync --frozen --no-dev

COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY backend/scripts ./scripts
COPY data /data
COPY evaluation /evaluation

RUN chmod +x /app/scripts/entrypoint.sh \
    && mkdir -p /data/uploads

EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
