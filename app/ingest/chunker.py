"""Split extracted snippets into chunks that fit within token budgets."""

from __future__ import annotations

from typing import List

from app.ingest.loader import Snippet


def chunk_snippets(
    snippets: List[Snippet],
    max_chars: int = 800,
    overlap_chars: int = 150,
) -> List[Snippet]:
    """Split large text snippets into smaller chunks with sliding overlap.

    Tables are never split — they pass through intact regardless of size.
    Text snippets longer than *max_chars* are split at paragraph boundaries.
    Each chunk (except the first) begins with the tail of the previous chunk
    (up to *overlap_chars*) so that evidence spanning a boundary is preserved.

    Returns a new list of Snippet dicts.
    """
    result: list[Snippet] = []

    for snippet in snippets:
        if snippet["type"] == "table":
            result.append(snippet)
            continue

        text = snippet["text"]
        if len(text) <= max_chars:
            result.append(snippet)
            continue

        # Split at paragraph boundaries (double newline or single newline)
        paragraphs = text.split("\n\n")
        if len(paragraphs) == 1:
            paragraphs = text.split("\n")

        chunk_texts: list[str] = []
        current_chunk: list[str] = []
        current_len = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if current_len + len(para) + 1 > max_chars and current_chunk:
                chunk_texts.append("\n".join(current_chunk))
                # Carry overlap into next chunk when overlap_chars > 0.
                # Note: flushed[-0:] returns the full string, so we guard explicitly.
                if overlap_chars > 0:
                    flushed = chunk_texts[-1]
                    if len(flushed) > overlap_chars:
                        tail = flushed[-overlap_chars:]
                        # Walk forward to the first space so the overlap starts cleanly
                        space_idx = tail.find(" ")
                        tail = tail[space_idx + 1:] if space_idx != -1 else tail
                    else:
                        tail = flushed
                    current_chunk = [tail] if tail else []
                    current_len = len(tail)
                else:
                    current_chunk = []
                    current_len = 0
            current_chunk.append(para)
            current_len += len(para) + 1

        if current_chunk:
            chunk_texts.append("\n".join(current_chunk))

        for chunk_idx, chunk_text in enumerate(chunk_texts):
            locator = snippet["locator"]
            if len(chunk_texts) > 1:
                locator = f"{locator} (part {chunk_idx + 1})"
            result.append(
                Snippet(locator=locator, text=chunk_text, type="text")
            )

    return result
