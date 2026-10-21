import random
from datetime import timedelta
from decimal import Decimal

import pytest

from app.knowledge import CATALOG, CONTINGENCY_WEIGHT, EXTRAS
from app.models import EventType
from app.planner import allocate, build_plan, build_timeline, is_budget_tight
from tests.conftest import TODAY


@pytest.mark.parametrize("event", list(EventType))
def test_catalog_weights_sum_to_100(event):
    assert sum(c.weight for c in CATALOG[event].values()) + CONTINGENCY_WEIGHT == 100


def test_allocate_always_sums_exactly():
    rng = random.Random(7)
    for _ in range(200):
        total = Decimal(rng.randint(1, 10**9)) / 100
        weights = {f"k{i}": Decimal(rng.randint(1, 40)) for i in range(rng.randint(1, 11))}
        assert sum(allocate(total, weights).values()) == total


@pytest.mark.parametrize("event", list(EventType))
def test_budget_sums_to_total_for_every_event(make_request, event):
    plan = build_plan(make_request(event_type=event, budget="99999.99"), TODAY)
    assert sum(line.amount for line in plan.budget) == Decimal("99999.99")


def test_contingency_is_always_reserved(make_request):
    plan = build_plan(make_request(), TODAY)
    assert any(line.key == "contingency" and line.share_pct >= 8 for line in plan.budget)


def test_context_adds_extra_categories_and_shrinks_others(make_request):
    base = build_plan(make_request(), TODAY)
    rich = build_plan(
        make_request(venue="outdoor", needs_accessibility=True, has_children=True), TODAY
    )
    keys = {line.key for line in rich.budget}
    assert set(EXTRAS) <= keys
    assert not set(EXTRAS) & {line.key for line in base.budget}
    base_catering = next(b for b in base.budget if b.key == "catering").amount
    rich_catering = next(b for b in rich.budget if b.key == "catering").amount
    assert rich_catering < base_catering


def test_birthday_children_do_not_add_kids_zone(make_request):
    plan = build_plan(make_request(event_type="birthday", has_children=True), TODAY)
    assert "kids_zone" not in {line.key for line in plan.budget}


def test_timeline_is_sorted_and_never_in_the_past(make_request):
    req = make_request(event_date=(TODAY + timedelta(days=10)).isoformat())
    timeline = build_timeline(req, TODAY)
    assert [t.due for t in timeline] == sorted(t.due for t in timeline)
    assert all(t.due >= TODAY for t in timeline)
    assert any(t.urgent for t in timeline)


def test_comfortable_lead_time_has_no_urgent_steps(make_request):
    req = make_request(event_date=(TODAY + timedelta(days=400)).isoformat())
    assert not any(t.urgent for t in build_timeline(req, TODAY))


def test_dietary_needs_extend_catering_checklist(make_request):
    plan = build_plan(make_request(dietary_needs=["nut_allergy", "vegan"]), TODAY)
    catering = next(v for v in plan.vendors if v.key == "catering")
    assert any("allergen" in item.lower() for item in catering.items)
    assert any("vegan" in item.lower() for item in catering.items)


def test_vendor_list_excludes_contingency(make_request):
    plan = build_plan(make_request(), TODAY)
    assert "contingency" not in {v.key for v in plan.vendors}


def test_tight_budget_warns(make_request):
    plan = build_plan(make_request(budget="10000"), TODAY)
    assert any("tight" in w for w in plan.warnings)


def test_realistic_budget_does_not_warn_tight(make_request):
    plan = build_plan(make_request(), TODAY)
    assert not any("tight" in w for w in plan.warnings)


def test_large_event_warns_about_safety(make_request):
    plan = build_plan(make_request(guest_count=800), TODAY)
    assert any("first-aid" in w for w in plan.warnings)


def test_fallback_ideas_use_theme_and_interests(make_request):
    plan = build_plan(make_request(theme="Retro", interests=["jazz", "chess"]), TODAY)
    text = " ".join(i.title for i in plan.ideas)
    assert "Retro" in text and "jazz" in text


def test_decisions_explain_every_context_rule(make_request):
    plan = build_plan(
        make_request(
            venue="outdoor",
            needs_accessibility=True,
            has_children=True,
            dietary_needs=["vegan"],
            event_date=(TODAY + timedelta(days=10)).isoformat(),
        ),
        TODAY,
    )
    text = " ".join(plan.decisions)
    for expected in (
        "contingency",
        "weather backup",
        "access provisions",
        "children",
        "vegan",
        "scheduled for today",
    ):
        assert expected in text


def test_baseline_decisions_mention_only_the_reserve(make_request):
    plan = build_plan(make_request(event_date=(TODAY + timedelta(days=400)).isoformat()), TODAY)
    assert len(plan.decisions) == 1 and "contingency" in plan.decisions[0]


def test_is_budget_tight_respects_currency(make_request):
    assert is_budget_tight(make_request(budget="10000"))
    assert not is_budget_tight(make_request(budget="10000", currency="USD", guest_count=100))
