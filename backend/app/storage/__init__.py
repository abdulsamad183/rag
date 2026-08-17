from app.storage.base import FileStorage
from app.storage.local import LocalFileStorage


def get_storage() -> FileStorage:
    """Storage factory. Local filesystem now; S3/MinIO/Azure/GCS adapters can
    be registered here without touching call sites (see docs/deployment.md)."""
    from app.config import get_settings

    settings = get_settings()
    if settings.storage_backend == "local":
        return LocalFileStorage(settings.storage_dir)
    raise ValueError(f"Unknown storage backend: {settings.storage_backend}")


__all__ = ["FileStorage", "LocalFileStorage", "get_storage"]
