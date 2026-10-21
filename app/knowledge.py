"""Planning knowledge as data, kept separate from the logic that applies it.

Weights are whole percentage points of the base budget and sum to 100 per event type
(enforced at import time and by tests). ``book_weeks`` is the latest sensible booking
lead time before the event.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import EventType


@dataclass(frozen=True, slots=True)
class Category:
    """A budget category: its share, booking lead time and vendor checklist."""

    label: str
    weight: int
    book_weeks: int
    checklist: tuple[str, ...] = ()


CONTINGENCY = "contingency"
LARGE_EVENT_GUESTS = 500
RUSH_DAYS = 14

EXTRA_REASONS: dict[str, str] = {
    "weather_backup": "Outdoor or mixed venue: {pct}% is set aside for a weather backup.",
    "accessibility": "Accessibility needs: {pct}% is set aside for access provisions.",
    "kids_zone": "Children are attending: {pct}% is set aside for a children's zone.",
}

CATALOG: dict[EventType, dict[str, Category]] = {
    EventType.WEDDING: {
        "venue": Category(
            "Venue & rentals",
            25,
            40,
            (
                "Visit at least 3 venues and compare total cost, not just hire fee",
                "Confirm capacity, power backup, parking and a rain or heat plan",
                "Get the cancellation and overtime terms in writing",
            ),
        ),
        "catering": Category(
            "Catering",
            30,
            26,
            (
                "Hold a tasting before signing",
                "Agree per-plate price, service staff count and wastage policy",
                "Confirm licences and hygiene certificates",
            ),
        ),
        "photography": Category(
            "Photography & video",
            10,
            40,
            (
                "Review full albums from real events, not highlight reels",
                "Agree delivery date, edited-photo count and raw-file rights",
            ),
        ),
        "attire": Category(
            "Attire & beauty",
            8,
            20,
            (
                "Book fittings with a buffer of at least two alterations",
                "Schedule hair and makeup trials",
            ),
        ),
        "decor": Category(
            "Decor & flowers",
            8,
            16,
            (
                "Share venue photos and colour palette with the decorator",
                "Confirm setup and teardown windows",
            ),
        ),
        "entertainment": Category(
            "Music & entertainment",
            6,
            20,
            ("Share a must-play and do-not-play list", "Confirm sound limits at the venue"),
        ),
        "stationery": Category(
            "Invitations & stationery",
            3,
            14,
            (
                "Proof every name, date and address twice",
                "Add a map link or QR code for directions",
            ),
        ),
    },
    EventType.BIRTHDAY: {
        "venue": Category(
            "Venue",
            20,
            6,
            (
                "Confirm the time slot includes setup and cleanup",
                "Check the venue's outside-food and decor rules",
            ),
        ),
        "catering": Category(
            "Food & drink",
            30,
            3,
            (
                "Order food for about 90% of RSVPs plus a small buffer",
                "Plan drinks and water separately from the meal",
            ),
        ),
        "decor": Category(
            "Decor",
            12,
            3,
            (
                "Choose one focal point such as a backdrop or balloon arch",
                "Prepare a simple setup checklist for helpers",
            ),
        ),
        "entertainment": Category(
            "Entertainment & activities",
            15,
            4,
            ("Match activities to the age range of the guests", "Keep a backup indoor activity"),
        ),
        "cake": Category(
            "Cake & desserts",
            8,
            2,
            (
                "Confirm size, flavour and allergen information",
                "Arrange pickup or delivery time and a cool place to store it",
            ),
        ),
        "favours": Category(
            "Invitations & favours", 5, 4, ("Send invites with a clear RSVP date",)
        ),
    },
    EventType.COMMUNITY: {
        "venue": Category(
            "Venue & permits",
            20,
            12,
            (
                "Apply for local permissions and any noise or road-use permits early",
                "Confirm event insurance and liability cover",
                "Walk the site and mark entrances, exits and first-aid point",
            ),
        ),
        "catering": Category(
            "Food & refreshments",
            25,
            6,
            (
                "Estimate attendance conservatively and plan for peak queue times",
                "Check food-stall hygiene licences",
            ),
        ),
        "av": Category(
            "Sound, stage & equipment",
            15,
            6,
            (
                "Test microphones and power before doors open",
                "Plan cable covers and a power backup",
            ),
        ),
        "promotion": Category(
            "Promotion & outreach",
            10,
            8,
            (
                "Publish date, place and access details in every channel",
                "Partner with local groups to extend reach",
            ),
        ),
        "entertainment": Category(
            "Programme & performers", 10, 8, ("Confirm performer slots and a changeover schedule",)
        ),
        "safety": Category(
            "Safety & first aid",
            5,
            4,
            (
                "Arrange trained first-aid cover and an incident log",
                "Brief volunteers on the emergency plan",
            ),
        ),
        "volunteers": Category(
            "Volunteers & supplies",
            5,
            3,
            (
                "Assign a named lead for each zone",
                "Provide identifiable vests or badges and a briefing",
            ),
        ),
    },
}

# Each base catalogue sums to 90 points; contingency adds the final 10.
CONTINGENCY_WEIGHT = 10
CONTINGENCY_CATEGORY = Category("Contingency reserve", CONTINGENCY_WEIGHT, 0)

# Context-triggered categories carved out of the base budget.
EXTRAS: dict[str, Category] = {
    "weather_backup": Category(
        "Weather backup",
        4,
        4,
        (
            "Book tent or covered space as a standby",
            "Set a go/no-go decision time based on the forecast",
        ),
    ),
    "accessibility": Category(
        "Accessibility provisions",
        3,
        6,
        (
            "Confirm step-free entry, accessible restrooms and seating",
            "Share accessibility details in the invitation",
        ),
    ),
    "kids_zone": Category(
        "Children's zone",
        4,
        4,
        (
            "Arrange supervised activities and a quiet corner",
            "Child-safe food and clear lost-and-found point",
        ),
    ),
}

TIMELINES: dict[EventType, tuple[tuple[int, str], ...]] = {
    EventType.WEDDING: (
        (52, "Fix budget, shortlist guests and agree priorities"),
        (44, "Book the venue and lock the date"),
        (36, "Book photographer and caterer"),
        (24, "Order attire and book entertainment"),
        (12, "Send invitations"),
        (8, "Finalise menu, decor and seating approach"),
        (4, "Confirm RSVPs and re-confirm every vendor"),
        (1, "Final headcount, run-of-show and payments"),
    ),
    EventType.BIRTHDAY: (
        (8, "Set budget, guest list and date"),
        (6, "Book venue and send invitations"),
        (4, "Order cake, decor and book entertainment"),
        (2, "Confirm RSVPs and finalise food quantities"),
        (1, "Buy supplies, confirm vendors and prepare the schedule"),
    ),
    EventType.COMMUNITY: (
        (14, "Define goals, audience and a lead team; request permits"),
        (10, "Book venue, equipment and key vendors"),
        (8, "Start promotion and recruit volunteers"),
        (6, "Confirm programme, performers and stalls"),
        (4, "Finalise safety, first-aid and crowd plan"),
        (2, "Brief volunteers and test equipment"),
        (1, "Final walk-through and send reminders"),
    ),
}

DIETARY_NOTES: dict[str, str] = {
    "vegetarian": "Confirm vegetarian dishes are prepared separately",
    "vegan": "Confirm clearly labelled vegan dishes, including desserts",
    "halal": "Confirm halal-certified suppliers and kitchen handling",
    "jain": "Confirm Jain-compliant preparation without root vegetables",
    "gluten_free": "Confirm gluten-free options and cross-contamination controls",
    "nut_allergy": "Get written allergen-handling confirmation and label all nut-containing items",
}

# Rough lower bound of per-guest spend (USD) below which plans tend to be unrealistic.
MIN_PER_GUEST_USD: dict[EventType, Decimal] = {
    EventType.WEDDING: Decimal(35),
    EventType.BIRTHDAY: Decimal(12),
    EventType.COMMUNITY: Decimal(4),
}
USD_PER_UNIT: dict[str, Decimal] = {
    "USD": Decimal(1),
    "EUR": Decimal("1.08"),
    "GBP": Decimal("1.27"),
    "INR": Decimal("0.012"),
}

BASE_IDEAS: dict[EventType, tuple[tuple[str, str], ...]] = {
    EventType.WEDDING: (
        ("Story-led ceremony", "Open with a short film or timeline of how the couple met."),
        ("Family recipe station", "Serve one dish from each family to personalise the menu."),
        ("Guest memory wall", "Let guests leave notes and photos for the couple to keep."),
    ),
    EventType.BIRTHDAY: (
        ("Signature activity", "Build the party around one activity the guest of honour loves."),
        ("Memory lane table", "Display photos from each year of life as a talking point."),
        ("DIY dessert bar", "Let guests decorate their own treats to keep them busy."),
    ),
    EventType.COMMUNITY: (
        ("Local makers market", "Invite neighbourhood artisans and small food stalls."),
        ("Story corner", "Host a recorded storytelling booth for residents."),
        ("Neighbour bingo", "A mixer card that encourages guests to meet new people."),
    ),
}


def _validate_catalog() -> None:
    """Fails fast at import if any event type's weights do not sum to 100."""
    for event, cats in CATALOG.items():
        total = sum(c.weight for c in cats.values()) + CONTINGENCY_WEIGHT
        if total != 100:
            raise RuntimeError(f"Budget weights for {event} sum to {total}, expected 100")


_validate_catalog()
