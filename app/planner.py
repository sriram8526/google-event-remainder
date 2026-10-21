"""Deterministic planning engine: budget, timeline, vendor checklist, warnings.

Everything here is a pure function of the request and an explicit ``today``, so the same
input always yields the same plan and each rule can be tested in isolation. The generative
layer (``services.py``) only adds creative ideas on top and is never needed for a valid plan.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

from .knowledge import (
    BASE_IDEAS,
    CATALOG,
    CONTINGENCY,
    CONTINGENCY_CATEGORY,
    DIETARY_NOTES,
    EXTRA_REASONS,
    EXTRAS,
    LARGE_EVENT_GUESTS,
    MIN_PER_GUEST_USD,
    TIMELINES,
    USD_PER_UNIT,
    Category,
)
from .models import (
    BudgetLine,
    EventType,
    Idea,
    Plan,
    PlanRequest,
    TimelineItem,
    VendorChecklist,
    Venue,
)

CENT = Decimal("0.01")


def allocate(total: Decimal, weights: dict[str, Decimal]) -> dict[str, Decimal]:
    """Splits ``total`` by ``weights`` using the largest-remainder method.

    Works in integer cents so the parts always sum exactly to the total.

    Args:
        total: Amount to split.
        weights: Relative weight per key; need not sum to any particular value.

    Returns:
        Amount per key, each rounded to cents, summing exactly to ``total``.
    """
    total_cents = int((total * 100).to_integral_value(ROUND_HALF_EVEN))
    weight_sum = sum(weights.values())
    raw = {k: Decimal(total_cents) * w / weight_sum for k, w in weights.items()}
    cents = {k: int(v) for k, v in raw.items()}
    leftover = total_cents - sum(cents.values())
    for key in sorted(raw, key=lambda k: raw[k] - cents[k], reverse=True)[:leftover]:
        cents[key] += 1
    return {k: Decimal(v).scaleb(-2) for k, v in cents.items()}


def _context_extras(req: PlanRequest) -> dict[str, Category]:
    """Categories that exist only because of this event's context."""
    extras: dict[str, Category] = {}
    if req.venue is not Venue.INDOOR:
        extras["weather_backup"] = EXTRAS["weather_backup"]
    if req.needs_accessibility:
        extras["accessibility"] = EXTRAS["accessibility"]
    if req.has_children and req.event_type is not EventType.BIRTHDAY:
        extras["kids_zone"] = EXTRAS["kids_zone"]
    return extras


def _categories(req: PlanRequest) -> dict[str, Category]:
    return {
        **CATALOG[req.event_type],
        CONTINGENCY: CONTINGENCY_CATEGORY,
        **_context_extras(req),
    }


def per_guest_budget(req: PlanRequest) -> Decimal:
    """Returns the budget per guest, rounded to cents."""
    return (req.budget / req.guest_count).quantize(CENT, ROUND_HALF_EVEN)


def is_budget_tight(req: PlanRequest) -> bool:
    """Returns True if the budget per guest is below a rough floor for this event type."""
    floor_usd = MIN_PER_GUEST_USD[req.event_type]
    return per_guest_budget(req) * USD_PER_UNIT[req.currency] < floor_usd


def build_budget(req: PlanRequest) -> list[BudgetLine]:
    """Splits the budget across categories, largest first.

    Args:
        req: The validated request.

    Returns:
        One line per category; amounts sum exactly to ``req.budget``.
    """
    cats = _categories(req)
    extra_points = sum(Decimal(cats[k].weight) for k in _context_extras(req))
    scale = (Decimal(100) - extra_points) / Decimal(100)
    weights = {
        key: Decimal(cat.weight) if key in EXTRAS else Decimal(cat.weight) * scale
        for key, cat in cats.items()
    }
    amounts = allocate(req.budget, weights)
    return [
        BudgetLine(
            key=key,
            label=cats[key].label,
            amount=amount,
            share_pct=round(float(amount / req.budget * 100), 1),
        )
        for key, amount in sorted(amounts.items(), key=lambda kv: kv[1], reverse=True)
    ]


def build_timeline(req: PlanRequest, today: date) -> list[TimelineItem]:
    """Works backwards from the event. Overdue steps move to today and are flagged."""
    items = []
    for weeks, task in TIMELINES[req.event_type]:
        due = req.event_date - timedelta(weeks=weeks)
        items.append(
            TimelineItem(due=max(due, today), weeks_before=weeks, task=task, urgent=due < today)
        )
    return sorted(items, key=lambda i: (i.due, -i.weeks_before))


def build_vendors(req: PlanRequest, budget: list[BudgetLine], today: date) -> list[VendorChecklist]:
    """Builds the vendor checklist, with booking deadlines and dietary additions."""
    cats = _categories(req)
    vendors = []
    for line in budget:
        if line.key == CONTINGENCY:
            continue
        cat = cats[line.key]
        items = list(cat.checklist)
        if line.key == "catering":
            items += [DIETARY_NOTES[d] for d in req.dietary_needs]
        due = req.event_date - timedelta(weeks=cat.book_weeks)
        vendors.append(
            VendorChecklist(
                key=line.key,
                label=cat.label,
                book_by=max(due, today),
                urgent=due < today,
                budget=line.amount,
                items=items,
            )
        )
    return sorted(vendors, key=lambda v: (v.book_by, v.label))


def build_decisions(
    req: PlanRequest, budget: list[BudgetLine], timeline: list[TimelineItem]
) -> list[str]:
    """Explains, in plain language, which rules shaped this plan."""
    shares = {line.key: line.share_pct for line in budget}
    decisions = [f"A {shares[CONTINGENCY]}% contingency reserve is held back for surprises."]
    decisions += [EXTRA_REASONS[key].format(pct=shares[key]) for key in _context_extras(req)]
    if req.dietary_needs:
        needs = ", ".join(d.replace("_", " ") for d in req.dietary_needs)
        decisions.append(f"The caterer checklist is extended for: {needs}.")
    overdue = sum(1 for t in timeline if t.urgent)
    if overdue:
        decisions.append(
            f"{overdue} step(s) were already past their ideal date, "
            "so they are scheduled for today."
        )
    return decisions


def build_warnings(req: PlanRequest, timeline: list[TimelineItem]) -> list[str]:
    """Returns risks the user should know about, most important first."""
    warnings = []
    if is_budget_tight(req):
        warnings.append(
            "Budget per guest is tight for this kind of event. Consider fewer guests, "
            "a simpler menu, or a lower-cost venue."
        )
    if any(t.urgent for t in timeline):
        warnings.append("Some steps are overdue. Book the highest-impact vendors first.")
    if req.guest_count >= LARGE_EVENT_GUESTS:
        warnings.append(
            "Large gatherings need a crowd-flow plan, security and first-aid cover. "
            "Consider hiring a professional event manager."
        )
    if req.venue is not Venue.INDOOR:
        warnings.append(
            "Outdoor elements depend on weather. Set a go/no-go time and a backup space."
        )
    return warnings


def fallback_ideas(req: PlanRequest) -> list[Idea]:
    """Returns built-in ideas, used whenever AI ideas are unavailable or not allowed."""
    ideas = [Idea(title=t, description=d) for t, d in BASE_IDEAS[req.event_type]]
    if req.theme:
        ideas.append(
            Idea(
                title=f"{req.theme}: one signature moment",
                description="Pick one memorable touch that expresses the theme "
                "instead of decorating everything.",
            )
        )
    ideas += [
        Idea(
            title=f"Build a moment around {interest}",
            description="Turn this interest into one activity, display or menu item.",
        )
        for interest in req.interests[:3]
    ]
    return ideas


def build_plan(req: PlanRequest, today: date) -> Plan:
    """Builds the full deterministic plan.

    Args:
        req: The validated request.
        today: The reference date, passed in so results are reproducible.

    Returns:
        The plan, including built-in ideas.
    """
    budget = build_budget(req)
    timeline = build_timeline(req, today)
    days_until = (req.event_date - today).days
    return Plan(
        summary=(
            f"{req.event_type.value.title()} for {req.guest_count} guests on "
            f"{req.event_date:%d %b %Y}, {days_until} days away."
        ),
        currency=req.currency,
        per_guest=per_guest_budget(req),
        days_until=days_until,
        budget=budget,
        timeline=timeline,
        vendors=build_vendors(req, budget, today),
        ideas=fallback_ideas(req),
        decisions=build_decisions(req, budget, timeline),
        warnings=build_warnings(req, timeline),
    )
