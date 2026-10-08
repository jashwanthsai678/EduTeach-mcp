"""Thin client for eduteach-simulation-host: stores a generated HTML page
(create_simulation) or a structured lesson-prep sheet (create_prep_sheet),
and returns a public URL. This client never renders anything itself.

One attempt, fails fast -- see core/exceptions.py for why this doesn't retry
internally.
"""

import httpx

from core.config import (
    HTTP_TIMEOUT_SECONDS,
    PREP_SHEET_TIMEOUT_SECONDS,
    SIMULATION_HOST_BASE,
)
from core.exceptions import UpstreamUnavailable


def create_simulation(html: str) -> dict:
    """Upload a complete, self-contained HTML page and get back a public URL."""
    url = f"{SIMULATION_HOST_BASE}/simulations"
    try:
        response = httpx.post(url, json={"html": html}, timeout=HTTP_TIMEOUT_SECONDS)
    except httpx.TimeoutException:
        raise UpstreamUnavailable(
            "The simulation hosting service didn't respond in time -- it's likely "
            "waking up from idle (free-tier cold start, ~20-30s). Wait a few "
            "seconds and try the same call again."
        )
    if response.status_code >= 500:
        raise UpstreamUnavailable(
            f"The simulation hosting service returned HTTP {response.status_code} -- "
            "likely still starting up. Wait a few seconds and try again."
        )
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise ValueError(f"Simulation rejected: {detail}")
    return response.json()


def create_prep_sheet(data: dict) -> dict:
    """Send the structured 6-bucket prep-sheet content and get back a public
    URL to the rendered PDF. `data` must match eduteach-simulation-host's
    PrepSheetRequest shape -- see that repo's app/main.py / README."""
    url = f"{SIMULATION_HOST_BASE}/prep-sheets"
    try:
        response = httpx.post(url, json=data, timeout=PREP_SHEET_TIMEOUT_SECONDS)
    except httpx.TimeoutException:
        raise UpstreamUnavailable(
            "The prep-sheet service didn't respond in time -- it's either waking "
            "up from idle (free-tier cold start, ~20-30s) or still rendering the "
            "PDF. Wait a few seconds and try the same call again."
        )
    if response.status_code >= 500:
        raise UpstreamUnavailable(
            f"The prep-sheet service returned HTTP {response.status_code} -- "
            "likely still starting up. Wait a few seconds and try again."
        )
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise ValueError(f"Prep sheet rejected: {detail}")
    return response.json()
