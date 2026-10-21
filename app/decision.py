"""Context decision engine: decides, before any model call, how much the model may do.

Mirrors the "route by context, fail to a deterministic path" pattern: the rules here are
plain code, so they are explainable and testable, and the user can be told why.
"""

from __future__ import annotations

from dataclasses import dataclass

from .knowledge import LARGE_EVENT_GUESTS, RUSH_DAYS
from .models import AiMode, PlanRequest

FULL_TEMPERATURE = 0.8
CONSERVATIVE_TEMPERATURE = 0.5
SKIP_AI_WITHIN_DAYS = 1


@dataclass(frozen=True, slots=True)
class AiDecision:
    """Outcome of the routing rules.

    Attributes:
        mode: How much the model may contribute.
        temperature: Sampling temperature to use.
        directives: Fixed instruction sentences (written by us, never by the user).
        rationale: Plain-language reason, shown to the user when AI is skipped.
    """

    mode: AiMode
    temperature: float
    directives: tuple[str, ...]
    rationale: str


def decide(req: PlanRequest, days_until: int, budget_tight: bool) -> AiDecision:
    """Chooses an AI mode and tailors instructions to the event's constraints.

    Args:
        req: The validated request.
        days_until: Whole days from today to the event.
        budget_tight: Whether the budget per guest is below the usual range.

    Returns:
        The routing decision.
    """
    if days_until <= SKIP_AI_WITHIN_DAYS:
        return AiDecision(
            AiMode.DETERMINISTIC,
            0.0,
            (),
            "The event is almost here, so the checklist matters more than new ideas.",
        )

    constrained = False
    directives: list[str] = []
    if days_until < RUSH_DAYS:
        constrained = True
        directives.append("Only suggest ideas that can be arranged in the time left.")
    if budget_tight:
        constrained = True
        directives.append("Favour low-cost and do-it-yourself ideas.")
    if req.guest_count >= LARGE_EVENT_GUESTS:
        constrained = True
        directives.append("Favour ideas that stay safe and manageable for a large crowd.")
    if req.has_children:
        directives.append("Keep ideas suitable for children.")
    if req.needs_accessibility:
        directives.append(
            "Make every idea usable by guests with mobility, vision or hearing needs."
        )

    if constrained:
        return AiDecision(AiMode.CONSERVATIVE, CONSERVATIVE_TEMPERATURE, tuple(directives), "")
    return AiDecision(AiMode.FULL, FULL_TEMPERATURE, tuple(directives), "")
