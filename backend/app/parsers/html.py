from __future__ import annotations

from bs4 import BeautifulSoup

from app.parsers.base import (
    BlockType,
    DocumentParser,
    ParsedBlock,
    ParsedDocument,
    decode_text,
    render_table_markdown,
)
from app.utils.text import clean_text

_SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form"}


class HtmlParser(DocumentParser):
    source_types = ("html",)

    def parse(self, data: bytes, filename: str) -> ParsedDocument:
        soup = BeautifulSoup(decode_text(data), "lxml")
        for tag in soup.find_all(_SKIP_TAGS):
            tag.decompose()

        title = clean_text(soup.title.get_text()) if soup.title else ""
        canonical = soup.find("link", rel="canonical")
        url = canonical.get("href", "") if canonical else ""
        if not url:
            og = soup.find("meta", property="og:url")
            url = og.get("content", "") if og else ""

        blocks: list[ParsedBlock] = []
        stack: list[tuple[int, str]] = []

        def section_path() -> str:
            return " > ".join(h for _, h in stack)

        body = soup.body or soup
        for element in body.find_all(
            ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "table", "blockquote"]
        ):
            if element.find_parent("table") is not None and element.name != "table":
                continue
            name = element.name
            if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                level = int(name[1])
                text = clean_text(element.get_text(" "))
                if not text:
                    continue
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, text))
                blocks.append(
                    ParsedBlock(
                        type=BlockType.HEADING, text=text, heading=text,
                        section_path=section_path(), heading_level=level,
                    )
                )
            elif name == "table":
                rows = [
                    [clean_text(cell.get_text(" ")) for cell in tr.find_all(["td", "th"])]
                    for tr in element.find_all("tr")
                ]
                rows = [r for r in rows if any(r)]
                if not rows:
                    continue
                headers, body_rows = rows[0], rows[1:]
                blocks.append(
                    ParsedBlock(
                        type=BlockType.TABLE,
                        text=render_table_markdown(headers, body_rows),
                        heading=stack[-1][1] if stack else "",
                        section_path=section_path(),
                        meta={"table": {"headers": headers, "rows": body_rows}},
                    )
                )
            elif name == "pre":
                text = element.get_text()
                if text.strip():
                    blocks.append(
                        ParsedBlock(
                            type=BlockType.CODE, text=text,
                            heading=stack[-1][1] if stack else "",
                            section_path=section_path(),
                        )
                    )
            else:
                text = clean_text(element.get_text(" "))
                if len(text) < 3:
                    continue
                blocks.append(
                    ParsedBlock(
                        type=BlockType.TEXT, text=text,
                        heading=stack[-1][1] if stack else "",
                        section_path=section_path(),
                    )
                )

        return ParsedDocument(
            title=title or filename,
            source_type="html",
            blocks=blocks,
            meta={"url": url, "title": title},
        )
