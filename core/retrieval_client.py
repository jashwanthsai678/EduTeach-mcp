"""Thin client for textbook-retrieval's semantic search API (POST /retrieve-content).

One attempt, fails fast -- see core/exceptions.py for why this doesn't retry
internally.
"""

import httpx

from core.config import HTTP_TIMEOUT_SECONDS, RETRIEVAL_API_BASE
from core.exceptions import UpstreamUnavailable


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
    try:
        response = httpx.post(url, json=payload, timeout=HTTP_TIMEOUT_SECONDS)
    except httpx.TimeoutException:
        raise UpstreamUnavailable(
            "The textbook search service didn't respond in time -- it's likely "
            "waking up from idle (free-tier cold start, ~20-30s) or busy calling "
            "its embedding provider. Wait a few seconds and try the same call again."
        )
    if response.status_code >= 500:
        raise UpstreamUnavailable(
            f"The textbook search service returned HTTP {response.status_code} -- "
            "likely still starting up. Wait a few seconds and try again."
        )
    response.raise_for_status()
    return response.json()
