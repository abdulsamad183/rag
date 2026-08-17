from __future__ import annotations

import asyncio
from pathlib import Path

from app.storage.base import FileStorage


class LocalFileStorage(FileStorage):
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        # Path-traversal protection: resolved path must stay inside root.
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid storage key (path traversal rejected)")
        return path

    async def save(self, key: str, data: bytes) -> str:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        return key

    async def read(self, key: str) -> bytes:
        return await asyncio.to_thread(self._resolve(key).read_bytes)

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)

    async def exists(self, key: str) -> bool:
        return self._resolve(key).exists()
