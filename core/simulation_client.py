"""Thin client for eduteach-simulation-host (stores a generated HTML page,
returns a public URL -- it never renders anything itself).

One attempt, fails fast -- see core/exceptions.py for why this doesn't retry
internally.
"""

import httpx

from core.config import HTTP_TIMEOUT_SECONDS, SIMULATION_HOST_BASE
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
