"""Shared utilities for the geo_ogc library modules."""
from __future__ import annotations

from urllib.parse import urlparse, urlunparse


def base_url(url: str) -> str:
    """Strip existing query parameters from *url* to obtain the service base URL."""
    parsed = urlparse(url)
    return urlunparse(parsed._replace(query=""))
