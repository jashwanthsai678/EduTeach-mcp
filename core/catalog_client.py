"""Thin client for eduteach-textbook-api (the read-only published-content REST API).

One attempt, fails fast -- see core/exceptions.py for why this doesn't retry
internally.
"""

import httpx

from core.config import CATALOG_API_BASE, HTTP_TIMEOUT_SECONDS
from core.exceptions import UpstreamUnavailable


def _get(path: str, params: dict | None = None) -> httpx.Response:
    url = f"{CATALOG_API_BASE}{path}"
    try:
        response = httpx.get(url, params=params, timeout=HTTP_TIMEOUT_SECONDS)
    except httpx.TimeoutException:
        raise UpstreamUnavailable(
            "The textbook catalog service didn't respond in time -- it's likely "
            "waking up from idle (free-tier cold start, ~20-30s). Wait a few "
            "seconds and try the same call again."
        )
    if response.status_code >= 500:
        raise UpstreamUnavailable(
            f"The textbook catalog service returned HTTP {response.status_code} -- "
            "likely still starting up. Wait a few seconds and try again."
        )
    return response


def list_books(
    board: str | None = None,
    grade: str | None = None,
    subject: str | None = None,
    language: str | None = None,
) -> list[dict]:
    """List every published book, optionally filtered. Mirrors GET /published/books."""
    params = {
        k: v
        for k, v in {"board": board, "grade": grade, "subject": subject, "language": language}.items()
        if v is not None
    }
    response = _get("/published/books", params=params)
    response.raise_for_status()
    return response.json()


def list_chapters(book_id: str) -> list[dict]:
    """List a book's published chapters (number, title, page range)."""
    response = _get(f"/published/books/{book_id}/chapters")
    response.raise_for_status()
    return response.json()


def get_chapter(book_id: str, chapter_number: int) -> dict:
    """Fetch one chapter's full content + resolved image URLs."""
    response = _get(f"/published/books/{book_id}/chapters/{chapter_number}")
    response.raise_for_status()
    return response.json()
