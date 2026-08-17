"""Generate the initial Alembic migration against a throwaway embedded postgres.

    uv run python scripts/gen_migration.py "initial schema"
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pgserver


def main() -> None:
    message = sys.argv[1] if len(sys.argv) > 1 else "auto"
    tmp = Path(tempfile.mkdtemp(prefix="ragmig"))
    server = pgserver.get_server(tmp / "data")
    try:
        server.psql("CREATE EXTENSION IF NOT EXISTS vector;")
        socket_dir = str(tmp / "data")
        url = f"postgresql+asyncpg://postgres@/postgres?host={socket_dir}"
        env = {**os.environ, "DATABASE_URL": url}
        subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, env=env)
        subprocess.run(
            ["uv", "run", "alembic", "revision", "--autogenerate", "-m", message],
            check=True,
            env=env,
        )
    finally:
        server.cleanup()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
