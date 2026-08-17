"""Upload validation: extension allow-list, size limits, safe filenames,
and content sniffing so a renamed executable can't masquerade as a PDF."""

from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath

from app.config import get_settings
from app.core.errors import FileTooLargeError, UnsupportedFileTypeError, ValidationFailed

ALLOWED_EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
    ".docx": "docx",
    ".html": "html",
    ".htm": "html",
    ".csv": "csv",
    ".json": "json",
    ".jsonl": "jsonl",
}

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._ -]")


def sanitize_filename(filename: str) -> str:
    name = PurePosixPath(filename.replace("\\", "/")).name  # strip any directory parts
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = _SAFE_CHARS.sub("_", name).strip(" .")
    if not name:
        raise ValidationFailed("Filename is empty or invalid")
    return name[:200]


def detect_source_type(filename: str) -> str:
    ext = PurePosixPath(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise UnsupportedFileTypeError(f"Unsupported file type '{ext}'. Allowed: {allowed}")
    return ALLOWED_EXTENSIONS[ext]


def validate_size(size_bytes: int) -> None:
    limit = get_settings().max_upload_bytes
    if size_bytes > limit:
        raise FileTooLargeError(
            f"File exceeds the {get_settings().max_upload_mb} MB upload limit",
            details={"size_bytes": size_bytes, "limit_bytes": limit},
        )
    if size_bytes == 0:
        raise ValidationFailed("File is empty")


def sniff_content(source_type: str, data: bytes) -> None:
    """Cheap magic-byte checks for binary formats; reject obvious mismatches."""
    head = data[:8]
    if source_type == "pdf" and not head.startswith(b"%PDF"):
        raise UnsupportedFileTypeError("File does not look like a valid PDF")
    if source_type == "docx" and not head.startswith(b"PK"):
        raise UnsupportedFileTypeError("File does not look like a valid DOCX")
    # Text formats: require decodable UTF-8/Latin-1 without NUL bytes
    if source_type in ("txt", "markdown", "html", "csv", "json", "jsonl") and b"\x00" in data[:4096]:
        raise UnsupportedFileTypeError("Binary content in a text-format upload")


def validate_upload(filename: str, data: bytes) -> tuple[str, str]:
    """Returns (safe_filename, source_type) or raises."""
    safe_name = sanitize_filename(filename)
    source_type = detect_source_type(safe_name)
    validate_size(len(data))
    sniff_content(source_type, data)
    return safe_name, source_type
