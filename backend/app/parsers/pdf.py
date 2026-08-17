from __future__ import annotations

import io

from pypdf import PdfReader

from app.core.errors import IngestionError
from app.parsers.base import BlockType, DocumentParser, ParsedBlock, ParsedDocument
from app.utils.text import clean_text, split_paragraphs


class PdfParser(DocumentParser):
    source_types = ("pdf",)

    def parse(self, data: bytes, filename: str) -> ParsedDocument:
        try:
            reader = PdfReader(io.BytesIO(data))
        except Exception as exc:  # noqa: BLE001
            raise IngestionError(f"Could not read PDF: {exc}") from exc

        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise IngestionError("PDF is password-protected") from exc

        meta = reader.metadata or {}
        title = (meta.title or "").strip() if meta else ""
        blocks: list[ParsedBlock] = []
        image_pages: list[int] = []

        for page_number, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:  # noqa: BLE001 — a single bad page must not kill the doc
                text = ""
            # Multimodal roadmap: record where visual elements live so a future
            # image/table extractor can revisit exactly these pages.
            try:
                if page.images:
                    image_pages.append(page_number)
            except Exception:  # noqa: BLE001
                pass
            text = clean_text(text)
            if not text:
                continue
            for paragraph in split_paragraphs(text):
                blocks.append(ParsedBlock(type=BlockType.TEXT, text=paragraph, page=page_number))

        if not blocks:
            raise IngestionError(
                "No extractable text found in PDF (it may be scanned images; OCR is on the roadmap)"
            )

        return ParsedDocument(
            title=title or filename,
            source_type="pdf",
            blocks=blocks,
            meta={
                "page_count": len(reader.pages),
                "author": (meta.author or "") if meta else "",
                "pages_with_images": image_pages,
            },
        )
