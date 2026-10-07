"""Thin client for textbook-retrieval's semantic search API (POST /retrieve-content)."""

import httpx

from core.config import HTTP_TIMEOUT_SECONDS, RETRIEVAL_API_BASE

_MAX_ATTEMPTS = 3


def retrieve_content(
    query: str,
    book_id: str | None = None,
    chapter: int | None = None,
    top_k_text: int = 5,
    top_k_images: int = 3,
) -> dict:
    """Semantic search over indexed textbook chunks + image captions.

    book_id/chapter are optional pre-filters -- when given, search is narrowed
    to that book (and chapter) before ranking, not applied after.
    """
    payload = {
        "query": query,
        "book_id": book_id,
        "chapter": chapter,
        "top_k_text": top_k_text,
        "top_k_images": top_k_images,
    }
    url = f"{RETRIEVAL_API_BASE}/retrieve-content"
    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = httpx.post(url, json=payload, timeout=HTTP_TIMEOUT_SECONDS)
            if response.status_code >= 500:
                last_exc = RuntimeError(f"{url} -> HTTP {response.status_code}")
                continue
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            last_exc = exc
    raise RuntimeError(f"retrieval API unreachable after {_MAX_ATTEMPTS} attempts: {url}") from last_exc
