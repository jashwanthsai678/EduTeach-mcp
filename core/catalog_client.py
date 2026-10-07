"""Thin client for eduteach-textbook-api (the read-only published-content REST API).

Retries on timeout/5xx because the upstream Render free-tier service cold-starts
slowly after inactivity -- same assumption textbook-retrieval's api_client.py makes.
"""

import httpx

from core.config import CATALOG_API_BASE, HTTP_TIMEOUT_SECONDS

_MAX_ATTEMPTS = 3


def _get(path: str, params: dict | None = None) -> httpx.Response:
    url = f"{CATALOG_API_BASE}{path}"
    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = httpx.get(url, params=params, timeout=HTTP_TIMEOUT_SECONDS)
            if response.status_code >= 500:
                last_exc = RuntimeError(f"{url} -> HTTP {response.status_code}")
                continue
            return response
        except httpx.TimeoutException as exc:
            last_exc = exc
    raise RuntimeError(f"catalog API unreachable after {_MAX_ATTEMPTS} attempts: {url}") from last_exc


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
