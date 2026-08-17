from __future__ import annotations

import re

from app.parsers.base import BlockType, DocumentParser, ParsedBlock, ParsedDocument, decode_text
from app.utils.text import clean_text

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE = re.compile(r"^(```|~~~)")


class MarkdownParser(DocumentParser):
    """Heading-aware Markdown parsing. Preserves the heading hierarchy in
    ``section_path`` and keeps fenced code blocks intact as code blocks."""

    source_types = ("markdown",)

    def parse(self, data: bytes, filename: str) -> ParsedDocument:
        text = decode_text(data)
        lines = text.split("\n")
        blocks: list[ParsedBlock] = []
        stack: list[tuple[int, str]] = []  # (level, heading)
        buffer: list[str] = []
        in_code = False
        code_buffer: list[str] = []
        title = ""

        def section_path() -> str:
            return " > ".join(h for _, h in stack)

        def current_heading() -> str:
            return stack[-1][1] if stack else ""

        def flush_text() -> None:
            content = clean_text("\n".join(buffer))
            buffer.clear()
            if content:
                for para in re.split(r"\n\s*\n", content):
                    if para.strip():
                        blocks.append(
                            ParsedBlock(
                                type=BlockType.TEXT,
                                text=para.strip(),
                                heading=current_heading(),
                                section_path=section_path(),
                            )
                        )

        for line in lines:
            if _FENCE.match(line.strip()):
                if in_code:
                    blocks.append(
                        ParsedBlock(
                            type=BlockType.CODE,
                            text="\n".join(code_buffer),
                            heading=current_heading(),
                            section_path=section_path(),
                        )
                    )
                    code_buffer.clear()
                    in_code = False
                else:
                    flush_text()
                    in_code = True
                continue
            if in_code:
                code_buffer.append(line)
                continue
            match = _HEADING.match(line)
            if match:
                flush_text()
                level = len(match.group(1))
                heading = match.group(2).strip()
                if not title and level == 1:
                    title = heading
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, heading))
                blocks.append(
                    ParsedBlock(
                        type=BlockType.HEADING,
                        text=heading,
                        heading=heading,
                        section_path=section_path(),
                        heading_level=level,
                    )
                )
            else:
                buffer.append(line)
        flush_text()
        if in_code and code_buffer:
            blocks.append(ParsedBlock(type=BlockType.CODE, text="\n".join(code_buffer)))

        return ParsedDocument(title=title or filename, source_type="markdown", blocks=blocks)
