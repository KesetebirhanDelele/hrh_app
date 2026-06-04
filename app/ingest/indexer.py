"""Build and query a snippet embedding index for RAG retrieval."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from openai import OpenAI


EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536
BATCH_SIZE = 100  # Keep batches under OpenAI's 300K token-per-request limit


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors without numpy.

    Kept for backward compatibility — tests import this directly.
    The retrieve() function uses numpy internally for speed.
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _embed_texts(texts: List[str], api_key: str, model: str = EMBEDDING_MODEL) -> List[List[float]]:
    """Embed a list of texts using OpenAI embeddings API, batching as needed."""
    client = OpenAI(api_key=api_key)
    all_embeddings: List[List[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        resp = client.embeddings.create(model=model, input=batch)
        sorted_data = sorted(resp.data, key=lambda x: x.index)
        all_embeddings.extend([d.embedding for d in sorted_data])

    return all_embeddings


def build_index(sources_path: str, output_path: Optional[str] = None) -> str:
    """Build an embedding index from a sources JSON file.

    Args:
        sources_path: Path to the sources JSON (e.g. eth_sources.json)
        output_path: Where to write the index. Defaults to sibling file with _index suffix.

    Returns:
        Path to the written index file.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to build an embedding index.")

    sources_p = Path(sources_path)
    raw = sources_p.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    sources_data = json.loads(text)

    sources = sources_data.get("sources", [])

    # Flatten all snippets with source metadata
    entries: List[Dict[str, Any]] = []
    for src in sources:
        source_id = src.get("source_id", "")
        source_title = src.get("source_title", "")
        for snip in src.get("snippets", []):
            snip_text = snip.get("text", "").strip()
            if not snip_text:
                continue
            entries.append({
                "source_id": source_id,
                "source_title": source_title,
                "locator": snip.get("locator", ""),
                "text": snip_text,
                "type": snip.get("type", "text"),
            })

    if not entries:
        raise ValueError("No snippets found in sources file.")

    print(f"  Embedding {len(entries)} snippets...")

    texts = [e["text"] for e in entries]
    embeddings = _embed_texts(texts, api_key)

    for entry, emb in zip(entries, embeddings):
        entry["embedding"] = emb

    if output_path is None:
        stem = sources_p.stem.replace("_sources", "")
        output_path = str(sources_p.parent / f"{stem}_index.json")

    index_data = {
        "model": EMBEDDING_MODEL,
        "snippet_count": len(entries),
        "snippets": entries,
    }

    Path(output_path).write_text(
        json.dumps(index_data, ensure_ascii=False), encoding="utf-8"
    )

    return output_path


def load_index(index_path: str) -> Dict[str, Any]:
    """Load an index file into memory."""
    raw = Path(index_path).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return json.loads(text)


def retrieve(
    index_data: Dict[str, Any],
    query: str,
    top_k: int = 20,
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve the top-K most relevant snippets for a query using numpy.

    Args:
        index_data: Loaded index (from load_index).
        query: The query text to search for.
        top_k: Number of results to return.
        api_key: OpenAI API key. Falls back to env var.

    Returns:
        List of snippet dicts with source_id, source_title, locator, text, type, score.
    """
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for retrieval.")

    query_embedding = _embed_texts([query], api_key, model=index_data.get("model", EMBEDDING_MODEL))[0]

    snippets = index_data.get("snippets", [])
    if not snippets:
        return []

    # Build normalised embedding matrix once — O(N·D) but only in numpy
    matrix = np.array([s["embedding"] for s in snippets], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    matrix = matrix / np.clip(norms, 1e-9, None)

    q = np.array(query_embedding, dtype=np.float32)
    q_norm = float(np.linalg.norm(q))
    if q_norm > 1e-9:
        q = q / q_norm

    scores: np.ndarray = matrix @ q  # shape (N,)

    k = min(top_k, len(snippets))
    top_indices = np.argpartition(scores, -k)[-k:]
    top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

    results: List[Dict[str, Any]] = []
    for idx in top_indices:
        snip = snippets[idx]
        results.append({
            "source_id": snip.get("source_id", ""),
            "source_title": snip.get("source_title", ""),
            "locator": snip.get("locator", ""),
            "text": snip.get("text", ""),
            "type": snip.get("type", "text"),
            "score": round(float(scores[idx]), 4),
        })

    return results


def group_by_source(snippets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group retrieved snippets back into source-level structure for allowed_sources.

    Returns a list of source dicts with source_id, source_title, and snippets array,
    matching the format expected by render_prompt_for_job.
    """
    sources: Dict[str, Dict[str, Any]] = {}
    for snip in snippets:
        sid = snip.get("source_id", "")
        if sid not in sources:
            sources[sid] = {
                "source_id": sid,
                "source_title": snip.get("source_title", ""),
                "snippets": [],
            }
        sources[sid]["snippets"].append({
            "locator": snip.get("locator", ""),
            "text": snip.get("text", ""),
            "type": snip.get("type", "text"),
        })

    return list(sources.values())


def build_retriever(index_data: Dict[str, Any], api_key: str = "") -> "HybridRetriever":
    """Factory: build a HybridRetriever from a loaded index dict.

    Constructs VectorIndex and BM25Index from the same snippet list, then
    wraps them in a HybridRetriever ready for per-query hybrid search.

    Args:
        index_data: Dict returned by load_index().
        api_key: OpenAI API key for query embedding. Falls back to env var.

    Returns:
        HybridRetriever instance.
    """
    from app.retrieve.bm25 import BM25Index
    from app.retrieve.retriever import HybridRetriever
    from app.retrieve.vector import VectorIndex

    api_key = api_key or os.getenv("OPENAI_API_KEY", "")
    snippets = index_data.get("snippets", [])
    model = index_data.get("model", EMBEDDING_MODEL)

    vector_idx = VectorIndex(snippets)
    bm25_idx = BM25Index(snippets)
    return HybridRetriever(vector_idx, bm25_idx, api_key=api_key, embedding_model=model)
