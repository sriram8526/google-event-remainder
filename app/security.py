"""Small, dependency-free security helpers: rate limiting and response headers."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

MAX_TRACKED_CLIENTS = 10_000

SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def client_ip(forwarded_for: str | None, peer: str | None, trusted_hops: int) -> str:
    """Identifies the client for rate limiting.

    Only trusts ``X-Forwarded-For`` entries added by proxies we control: with N trusted
    proxies, the Nth entry from the right is the address the outermost one saw. Anything the
    client prepended sits further left and is ignored.

    Args:
        forwarded_for: Raw ``X-Forwarded-For`` header, if any.
        peer: The directly connected address.
        trusted_hops: Number of trusted reverse proxies (0 disables header use).

    Returns:
        A string key for the client.
    """
    if trusted_hops > 0 and forwarded_for:
        parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
        if len(parts) >= trusted_hops:
            return parts[-trusted_hops]
    return peer or "unknown"


class SlidingWindowRateLimiter:
    """In-memory per-client limiter. Use a shared store (e.g. Redis) when running many instances."""

    def __init__(
        self, limit: int, window_s: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._limit, self._window, self._clock = limit, window_s, clock
        self._hits: dict[str, deque[float]] = {}

    def check(self, client: str) -> float:
        """Records a hit. Returns 0 if allowed, otherwise seconds until the client may retry."""
        now = self._clock()
        if len(self._hits) >= MAX_TRACKED_CLIENTS:
            self._evict(now)
        hits = self._hits.setdefault(client, deque())
        while hits and now - hits[0] >= self._window:
            hits.popleft()
        if len(hits) >= self._limit:
            return max(self._window - (now - hits[0]), 0.0)
        hits.append(now)
        return 0.0

    def _evict(self, now: float) -> None:
        stale = [c for c, h in self._hits.items() if not h or now - h[-1] >= self._window]
        for client in stale:
            del self._hits[client]
