"""Model adapters. The rest of the app depends only on ``TextGenerationPort``.

Keeping the vendor SDK behind a port (dependency inversion) means the domain logic never
imports Gemini details, and tests can inject a deterministic fake instead of mocking HTTP.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_OUTPUT_TOKENS = 2048


class TextGenerationPort(Protocol):
    """Anything that can turn a prompt into JSON text, or fail safely with ``None``."""

    async def generate(
        self, system_prompt: str, user_prompt: str, temperature: float
    ) -> str | None:
        """Returns the model's text, or None on any failure."""
        ...

    async def aclose(self) -> None:
        """Releases network resources."""
        ...


class NullTextGenerator:
    """Used when no API key is configured; always declines so callers use the fallback."""

    async def generate(
        self, system_prompt: str, user_prompt: str, temperature: float
    ) -> str | None:
        """Always returns None."""
        return None

    async def aclose(self) -> None:
        """Nothing to release."""


class GeminiTextGenerator:
    """Calls the Gemini REST API with a timeout and a cap on concurrent requests."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_s: float,
        max_concurrent: int = 4,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._url = ENDPOINT.format(model=model)
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self._slots = asyncio.Semaphore(max_concurrent)

    async def generate(
        self, system_prompt: str, user_prompt: str, temperature: float
    ) -> str | None:
        """Returns the model's JSON text, or None if saturated, failed or malformed.

        When every slot is busy the request is shed immediately instead of queued, so a
        burst of traffic cannot build an unbounded backlog of paid calls.
        """
        if self._slots.locked():
            logger.warning("Gemini concurrency limit reached; using fallback")
            return None
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
                "responseMimeType": "application/json",
            },
        }
        async with self._slots:
            try:
                response = await self._client.post(
                    self._url, json=body, headers={"x-goog-api-key": self._api_key}
                )
                response.raise_for_status()
                text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                # Log only the exception type: messages can echo request details.
                logger.warning("Gemini request failed: %s", type(exc).__name__)
                return None
        return text if isinstance(text, str) else None

    async def aclose(self) -> None:
        """Closes the shared HTTP client."""
        await self._client.aclose()
