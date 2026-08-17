import pytest

from app.core.errors import FileTooLargeError, UnsupportedFileTypeError, ValidationFailed
from app.security.files import (
    detect_source_type,
    sanitize_filename,
    sniff_content,
    validate_upload,
)


def test_sanitize_strips_traversal():
    assert ".." not in sanitize_filename("../../etc/passwd")
    assert "/" not in sanitize_filename("a/b/c.txt")
    assert sanitize_filename("report final v2.pdf").endswith(".pdf")


def test_sanitize_rejects_empty():
    with pytest.raises(ValidationFailed):
        sanitize_filename("...")


def test_detect_source_type():
    assert detect_source_type("a.pdf") == "pdf"
    assert detect_source_type("a.md") == "markdown"
    assert detect_source_type("a.html") == "html"
    assert detect_source_type("a.jsonl") == "jsonl"


def test_detect_unsupported_extension_raises():
    with pytest.raises(UnsupportedFileTypeError):
        detect_source_type("malware.exe")


def test_sniff_rejects_fake_pdf():
    with pytest.raises(UnsupportedFileTypeError):
        sniff_content("pdf", b"this is not a pdf")


def test_sniff_accepts_real_pdf_magic():
    sniff_content("pdf", b"%PDF-1.7 rest of file")


def test_validate_upload_size_limit():
    huge = b"x" * (60 * 1024 * 1024)  # default limit is 50 MB
    with pytest.raises(FileTooLargeError):
        validate_upload("big.txt", huge)


def test_validate_upload_empty_rejected():
    with pytest.raises(ValidationFailed):
        validate_upload("empty.txt", b"")


def test_validate_upload_ok():
    name, source_type = validate_upload("Notes.TXT", b"hello world")
    assert source_type == "txt"
    assert name.lower().endswith(".txt")
