from __future__ import annotations

import json

from app.core.errors import IngestionError
from app.parsers.base import BlockType, DocumentParser, ParsedBlock, ParsedDocument, decode_text

MAX_OBJECTS = 2000


def _flatten(obj: object, prefix: str = "") -> list[str]:
    lines: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict | list):
                lines.extend(_flatten(value, path))
            else:
                lines.append(f"{path}: {value}")
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            lines.extend(_flatten(item, f"{prefix}[{index}]"))
    else:
        lines.append(f"{prefix}: {obj}")
    return lines


class JsonParser(DocumentParser):
    """JSON / JSONL. Arrays of objects become one block per object with its
    index preserved in metadata; nested values keep their JSON path."""

    source_types = ("json", "jsonl")

    def parse(self, data: bytes, filename: str) -> ParsedDocument:
        text = decode_text(data).strip()
        is_jsonl = filename.lower().endswith(".jsonl")
        items: list[object]
        try:
            if is_jsonl:
                items = [json.loads(line) for line in text.splitlines() if line.strip()]
            else:
                try:
                    parsed = json.loads(text)
                    items = parsed if isinstance(parsed, list) else [parsed]
                except json.JSONDecodeError:
                    # .json extension but JSONL content — accept it anyway
                    items = [json.loads(line) for line in text.splitlines() if line.strip()]
        except json.JSONDecodeError as exc:
            raise IngestionError(f"Invalid JSON: {exc}") from exc

        blocks: list[ParsedBlock] = []
        for index, item in enumerate(items[:MAX_OBJECTS]):
            lines = _flatten(item)
            if not lines:
                continue
            blocks.append(
                ParsedBlock(
                    type=BlockType.TEXT,
                    text="\n".join(lines),
                    meta={"object_index": index},
                )
            )
        return ParsedDocument(
            title=filename,
            source_type="jsonl" if is_jsonl else "json",
            blocks=blocks,
            meta={"object_count": len(items)},
        )
