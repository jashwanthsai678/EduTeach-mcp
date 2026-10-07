"""Fetches real image bytes so Claude can actually view a textbook image
(via vision) before deciding whether to include it -- rather than only ever
judging relevance from its caption text.
"""

import mimetypes
from urllib.parse import urlparse

import httpx

from core.config import HTTP_TIMEOUT_SECONDS
from core.exceptions import UpstreamUnavailable

# Every image URL returned by get_chapter/search_textbook points at a
# Supabase Storage bucket. This tool fetches whatever URL it's given, so it
# must not become an open proxy for arbitrary URLs.
_ALLOWED_HOST_SUFFIXES = (".supabase.co",)


class DisallowedImageHost(Exception):
    """Raised when asked to fetch a URL that isn't a known textbook-image host."""


def fetch_image(url: str) -> tuple[bytes, str]:
    """Download an image and return (raw_bytes, mime_type)."""
    host = urlparse(url).hostname or ""
    if not any(host.endswith(suffix) for suffix in _ALLOWED_HOST_SUFFIXES):
        raise DisallowedImageHost(
            f"Refusing to fetch an image from host '{host}'. Only use a `url` "
            "value exactly as returned by get_chapter or search_textbook, not "
            "an arbitrary external URL."
        )
    try:
        response = httpx.get(url, timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=True)
    except httpx.TimeoutException:
        raise UpstreamUnavailable(
            "The image storage service didn't respond in time. Wait a few "
            "seconds and try again."
        )
    if response.status_code >= 500:
        raise UpstreamUnavailable(
            f"The image storage service returned HTTP {response.status_code}. "
            "Wait a few seconds and try again."
        )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    mime_type = content_type or mimetypes.guess_type(url)[0] or "image/jpeg"
    return response.content, mime_type
