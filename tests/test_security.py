import pytest

from app.security import SlidingWindowRateLimiter, client_ip


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def test_limiter_blocks_then_recovers():
    clock = Clock()
    limiter = SlidingWindowRateLimiter(2, 10, clock)
    assert limiter.check("a") == 0 and limiter.check("a") == 0
    assert limiter.check("a") > 0
    clock.now = 10.1
    assert limiter.check("a") == 0


def test_limiter_isolates_clients():
    limiter = SlidingWindowRateLimiter(1, 10, Clock())
    assert limiter.check("a") == 0 and limiter.check("b") == 0


@pytest.mark.parametrize(
    ("forwarded", "peer", "hops", "expected"),
    [
        (None, "10.0.0.1", 0, "10.0.0.1"),
        ("6.6.6.6", "10.0.0.1", 0, "10.0.0.1"),  # header ignored when no proxy is trusted
        ("203.0.113.7", "10.0.0.1", 1, "203.0.113.7"),
        ("6.6.6.6, 203.0.113.7", "10.0.0.1", 1, "203.0.113.7"),  # client-prepended spoof ignored
        ("203.0.113.7, 10.9.9.9", "10.0.0.1", 2, "203.0.113.7"),
        ("203.0.113.7", "10.0.0.1", 3, "10.0.0.1"),  # fewer hops than expected: do not trust
        (None, None, 0, "unknown"),
    ],
)
def test_client_ip_only_trusts_configured_proxy_hops(forwarded, peer, hops, expected):
    assert client_ip(forwarded, peer, hops) == expected


def test_limiter_evicts_idle_clients_when_the_table_is_full(monkeypatch):
    monkeypatch.setattr("app.security.MAX_TRACKED_CLIENTS", 3)
    clock = Clock()
    limiter = SlidingWindowRateLimiter(5, 10, clock)
    for name in ("a", "b", "c"):
        limiter.check(name)
    clock.now = 11
    limiter.check("d")
    assert set(limiter._hits) == {"d"}
