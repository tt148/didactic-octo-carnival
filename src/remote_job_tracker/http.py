"""Polite shared HTTP fetching for public job feeds."""

from __future__ import annotations

import time
import urllib.request
from threading import Lock

USER_AGENT = "RemoteJobMarketTracker/0.1 (personal portfolio project)"
REQUEST_INTERVAL_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 25

_request_lock = Lock()
_last_request_at = 0.0


def fetch_bytes(url: str) -> bytes:
    """Fetch a URL with a descriptive User-Agent and a one-request-per-second limit."""
    global _last_request_at
    with _request_lock:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < REQUEST_INTERVAL_SECONDS:
            time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        _last_request_at = time.monotonic()
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read()
        return payload
