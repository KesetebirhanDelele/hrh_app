"""Split extracted snippets into chunks that fit within token budgets."""

from __future__ import annotations

from typing import List

from app.ingest.loader import Snippet


def chunk_snippets(
    snippets: List[Snippet],
    max_chars: int = 2000,
) -> List[Snippet]:
    """Split large text snippets into smaller chunks.

    Tables are never split — they pass through intact regardless of size.
    Text snippets longer than *max_chars* are split at paragraph boundaries.

    Returns a new list of Snippet dicts.
    """
    result: list[Snippet] = []

    for snippet in snippets:
        if snippet["type"] == "table":
            # Keep tables intact
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
            # If adding this paragraph would exceed limit, flush current chunk
            if current_len + len(para) + 1 > max_chars and current_chunk:
                chunk_texts.append("\n".join(current_chunk))
                current_chunk = []
                current_len = 0
            current_chunk.append(para)
            current_len += len(para) + 1  # +1 for newline

        if current_chunk:
            chunk_texts.append("\n".join(current_chunk))

        # Create snippets for each chunk
        for chunk_idx, chunk_text in enumerate(chunk_texts):
            locator = snippet["locator"]
            if len(chunk_texts) > 1:
                locator = f"{locator} (part {chunk_idx + 1})"
            result.append(
                Snippet(locator=locator, text=chunk_text, type="text")
            )

    return result
