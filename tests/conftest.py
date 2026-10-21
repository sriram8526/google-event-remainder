import re
from collections.abc import Callable
from datetime import date, timedelta

import pytest

from app.models import PlanRequest

TODAY = date.today()


def make_payload(**overrides):
    payload = {
        "event_type": "wedding",
        "guest_count": 150,
        "budget": "1200000",
        "currency": "INR",
        "event_date": (TODAY + timedelta(days=120)).isoformat(),
    }
    payload.update(overrides)
    return payload


class FakeGenerator:
    """Deterministic stand-in for the model (state testing, no network, no mock assertions)."""

    def __init__(self, responder: Callable[[str, str, float], str | None] | None = None):
        self.responder = responder or (lambda *_: IDEAS_JSON)
        self.calls: list[tuple[str, str, float]] = []

    async def generate(self, system_prompt, user_prompt, temperature):
        self.calls.append((system_prompt, user_prompt, temperature))
        return self.responder(system_prompt, user_prompt, temperature)

    async def aclose(self):
        return None


def leak_canary(system_prompt, _user, _temp):
    token = re.search(r"CANARY_[0-9a-f]{16}", system_prompt).group(0)
    return f'{{"ideas":[{{"title":"Secret {token}","description":"Leaked"}}]}}'


IDEAS_JSON = (
    '{"ideas":[{"title":"Lantern walk","description":"Guests carry paper lanterns to the venue."},'
    '{"title":"Story jars","description":"Guests drop in memories to read later."}]}'
)


@pytest.fixture
def make_request():
    return lambda **kw: PlanRequest(**make_payload(**kw))
