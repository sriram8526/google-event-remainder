from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.models import PlanRequest
from tests.conftest import TODAY, make_payload


@pytest.mark.parametrize(
    "override",
    [
        {"guest_count": 0},
        {"guest_count": 5001},
        {"budget": "0"},
        {"budget": "-5"},
        {"budget": "10.123"},
        {"currency": "XXX"},
        {"event_type": "funeral"},
        {"event_date": (TODAY - timedelta(days=1)).isoformat()},
        {"event_date": (TODAY + timedelta(days=3000)).isoformat()},
        {"location": "x" * 81},
        {"interests": ["a"] * 9},
        {"interests": ["x" * 41]},
        {"dietary_needs": ["pizza"]},
        {"unexpected": "field"},
    ],
)
def test_invalid_requests_are_rejected(override):
    with pytest.raises(ValidationError):
        PlanRequest(**make_payload(**override))


def test_dietary_needs_are_deduplicated_and_sorted():
    req = PlanRequest(**make_payload(dietary_needs=["vegan", "halal", "vegan"]))
    assert req.dietary_needs == ["halal", "vegan"]


def test_today_is_a_valid_event_date():
    assert PlanRequest(**make_payload(event_date=TODAY.isoformat()))
