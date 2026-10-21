from app.decision import CONSERVATIVE_TEMPERATURE, FULL_TEMPERATURE, decide
from app.models import AiMode


def test_comfortable_event_gets_full_mode(make_request):
    decision = decide(make_request(), 120, budget_tight=False)
    assert decision.mode is AiMode.FULL and decision.temperature == FULL_TEMPERATURE


def test_event_within_a_day_skips_the_model(make_request):
    decision = decide(make_request(), 1, budget_tight=False)
    assert decision.mode is AiMode.DETERMINISTIC and decision.rationale


def test_rush_tight_budget_and_large_crowd_are_conservative(make_request):
    assert decide(make_request(), 5, False).mode is AiMode.CONSERVATIVE
    assert decide(make_request(), 120, True).mode is AiMode.CONSERVATIVE
    big = decide(make_request(guest_count=800), 120, False)
    assert big.mode is AiMode.CONSERVATIVE and big.temperature == CONSERVATIVE_TEMPERATURE


def test_children_and_accessibility_shape_directives_without_changing_mode(make_request):
    decision = decide(make_request(has_children=True, needs_accessibility=True), 120, False)
    text = " ".join(decision.directives)
    assert decision.mode is AiMode.FULL and "children" in text and "hearing" in text
