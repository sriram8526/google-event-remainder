"""Runtime configuration, read once from the environment."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable settings. The API key is excluded from ``repr`` so it can never leak into logs.

    ``trusted_proxy_hops`` is the number of reverse proxies in front of the app (for example 1
    on Cloud Run). It is 0 by default so a client can never spoof its address.
    """

    gemini_api_key: str | None = field(default=None, repr=False)
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_s: float = 12.0
    rate_limit_requests: int = 30
    rate_limit_window_s: int = 60
    max_body_bytes: int = 16_384
    max_concurrent_ai: int = 4
    trusted_proxy_hops: int = 0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Builds settings from environment variables, using defaults for anything unset."""
        env = os.environ if env is None else env
        d = cls()  # defaults live on an instance because slots hide class-level values
        return cls(
            gemini_api_key=env.get("GEMINI_API_KEY") or None,
            gemini_model=env.get("GEMINI_MODEL", d.gemini_model),
            gemini_timeout_s=float(env.get("GEMINI_TIMEOUT_S", d.gemini_timeout_s)),
            rate_limit_requests=int(env.get("RATE_LIMIT_REQUESTS", d.rate_limit_requests)),
            rate_limit_window_s=int(env.get("RATE_LIMIT_WINDOW_S", d.rate_limit_window_s)),
            max_concurrent_ai=int(env.get("MAX_CONCURRENT_AI", d.max_concurrent_ai)),
            trusted_proxy_hops=int(env.get("TRUSTED_PROXY_HOPS", d.trusted_proxy_hops)),
        )
