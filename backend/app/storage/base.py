from __future__ import annotations

from abc import ABC, abstractmethod


class FileStorage(ABC):
    """Binary document storage. Keys are opaque relative paths chosen by the
    application (``{collection_id}/{document_id}/v{n}/{filename}``)."""

    @abstractmethod
    async def save(self, key: str, data: bytes) -> str:
        """Store bytes under key; return storage path/URI."""

    @abstractmethod
    async def read(self, key: str) -> bytes: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...
