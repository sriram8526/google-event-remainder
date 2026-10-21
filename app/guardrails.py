"""Deterministic guardrails that run outside the language model.

They map to the OWASP Top 10 for LLM Applications: prompt injection (LLM01), sensitive
information disclosure (LLM02), improper output handling (LLM05) and system prompt leakage
(LLM07). Nothing here depends on the model behaving well.
"""

from __future__ import annotations

import re
import secrets

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:ignore|disregard|forget)\s+(?:all\s+|any\s+|the\s+)*(?:previous|prior|above|earlier|system)\b",
        r"(?:reveal|show|print|repeat|leak)\s+(?:your\s+|the\s+)*(?:system\s+prompt|instructions|rules)",
        r"\bsystem\s+prompt\b",
        r"\byou\s+are\s+now\b",
        r"\b(?:jailbreak|developer\s+mode)\b",
        r"</?\s*(?:system|assistant|instruction|event_details)\b",
    )
)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_API_KEY = re.compile(r"\b(?:AIza[0-9A-Za-z_-]{35}|sk-[A-Za-z0-9_-]{20,})\b")
# Ten or more digits, possibly separated by spaces, dots, dashes or brackets: phones and cards.
_LONG_NUMBER = re.compile(r"(?<!\w)(?:\+?\d[\s().-]?){10,19}(?!\w)")


def looks_like_injection(text: str) -> bool:
    """Returns True if ``text`` resembles an attempt to override model instructions."""
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)


def scrub_pii(text: str) -> str:
    """Replaces emails, long digit runs (phones, cards) and API-key-like strings."""
    text = _API_KEY.sub("[redacted key]", text)
    text = _EMAIL.sub("[redacted email]", text)
    return _LONG_NUMBER.sub("[redacted number]", text)


def screen_text(text: str) -> tuple[str, bool]:
    """Prepares user free text for the model.

    Args:
        text: A free-text field supplied by the user.

    Returns:
        ``(clean_text, flagged)``. A flagged field comes back empty so it never reaches
        the model; the deterministic plan is unaffected.
    """
    if looks_like_injection(text):
        return "", True
    return scrub_pii(text), False


def new_canary() -> str:
    """Returns a random per-request token to embed in the system prompt."""
    return f"CANARY_{secrets.token_hex(8)}"


def leaks_canary(model_output: str, canary: str) -> bool:
    """Returns True if the model repeated the canary, which signals prompt leakage."""
    return canary.lower() in model_output.lower()
