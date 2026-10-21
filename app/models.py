"""Request and response schemas.

Validation here is the first security boundary: every field is typed and bounded,
free text has a length cap, option fields are closed sets, and unknown fields are rejected.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Currency = Literal["INR", "USD", "EUR", "GBP"]
Dietary = Literal["vegetarian", "vegan", "halal", "jain", "gluten_free", "nut_allergy"]
Interest = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]

MAX_PLANNING_HORIZON = timedelta(days=5 * 365)


class EventType(StrEnum):
    """Kinds of event the planner supports."""

    WEDDING = "wedding"
    BIRTHDAY = "birthday"
    COMMUNITY = "community"


class Venue(StrEnum):
    """Where the event takes place."""

    INDOOR = "indoor"
    OUTDOOR = "outdoor"
    HYBRID = "hybrid"


class PlanRequest(BaseModel):
    """What the user tells us about their event."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    event_type: EventType
    guest_count: int = Field(ge=1, le=5000)
    budget: Decimal = Field(gt=0, le=Decimal("100000000"), decimal_places=2)
    currency: Currency = "INR"
    event_date: date
    location: str = Field(default="", max_length=80)
    theme: str = Field(default="", max_length=80)
    venue: Venue = Venue.INDOOR
    interests: list[Interest] = Field(default_factory=list, max_length=8)
    dietary_needs: list[Dietary] = Field(default_factory=list, max_length=6)
    needs_accessibility: bool = False
    has_children: bool = False

    @field_validator("event_date")
    @classmethod
    def _date_in_range(cls, value: date) -> date:
        today = date.today()
        if value < today:
            raise ValueError("Event date must be today or later.")
        if value - today > MAX_PLANNING_HORIZON:
            raise ValueError("Event date must be within the next 5 years.")
        return value

    @field_validator("dietary_needs")
    @classmethod
    def _unique_sorted(cls, value: list[str]) -> list[str]:
        return sorted(set(value))


class AiMode(StrEnum):
    """How much the generative model is allowed to contribute to a request."""

    FULL = "full"
    CONSERVATIVE = "conservative"
    DETERMINISTIC = "deterministic"


class _Out(BaseModel):
    """Base for immutable response models."""

    model_config = ConfigDict(frozen=True)


class BudgetLine(_Out):
    """One category of the budget split."""

    key: str
    label: str
    amount: Decimal
    share_pct: float


class TimelineItem(_Out):
    """A dated planning step."""

    due: date
    weeks_before: int
    task: str
    urgent: bool


class VendorChecklist(_Out):
    """Checklist for one vendor category."""

    key: str
    label: str
    book_by: date
    urgent: bool
    budget: Decimal
    items: list[str]


class Idea(_Out):
    """A creative suggestion for the event."""

    title: str
    description: str


class Plan(_Out):
    """The deterministic plan returned by ``/api/plan``."""

    summary: str
    currency: Currency
    per_guest: Decimal
    days_until: int
    budget: list[BudgetLine]
    timeline: list[TimelineItem]
    vendors: list[VendorChecklist]
    ideas: list[Idea]
    decisions: list[str]
    warnings: list[str]


class IdeasResponse(_Out):
    """Personalised ideas returned by ``/api/ideas``, with an honest account of their origin."""

    ideas: list[Idea]
    ai_generated: bool
    mode: AiMode
    notice: str
