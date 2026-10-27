import hashlib
import json
from dataclasses import dataclass
from uuid import UUID, uuid5


@dataclass(frozen=True)
class Chunk:
    id: UUID
    ordinal: int
    start: int
    end: int
    page: int | None
    location: str
    text: str


def version(text, structure, settings, method):
    return hashlib.sha256(
        json.dumps(
            [
                1,
                text,
                structure,
                settings.rag_chunk_characters,
                method,
                settings.openai_embedding_model if method == "semantic_pgvector" else None,
                settings.embedding_dimensions if method == "semantic_pgvector" else None,
            ],
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()


def chunks(identifier: UUID, text: str, structure: list, size=1000) -> list[Chunk]:
    # Never cross PDF pages. Other structural references identify the containing block.
    pages = [s for s in structure if s["kind"] == "page"]
    spans = pages or [dict(start=0, end=len(text), kind="text", number=1)]
    result = []
    for span in spans:
        start, end = span["start"], span["end"]
        while start < end:
            stop = min(start + size, end)
            if stop < end:
                boundary = text.rfind(" ", start + size // 2, stop)
                if boundary > start:
                    stop = boundary
            value = text[start:stop]
            if value.strip():
                block = next((s for s in structure if s["start"] <= start < s["end"]), span)
                location = f"{block['kind']} {block['number']} · characters {start}–{stop}"
                key = hashlib.sha256(f"v1:{start}:{stop}:{value}".encode()).hexdigest()
                result.append(
                    Chunk(
                        uuid5(identifier, key),
                        len(result),
                        start,
                        stop,
                        span["number"] if pages else None,
                        location,
                        value,
                    )
                )
            if stop == end:
                break
            start = max(start + 1, stop - size // 6)
    return result
