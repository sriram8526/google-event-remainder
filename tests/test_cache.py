from app.cache import TTLCache


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def test_entries_expire():
    clock = Clock()
    cache = TTLCache[int](4, 10, clock)
    cache.put("a", 1)
    assert cache.get("a") == 1
    clock.now = 10.1
    assert cache.get("a") is None and len(cache) == 0


def test_least_recently_used_entry_is_evicted():
    cache = TTLCache[int](2, 100, Clock())
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")
    cache.put("c", 3)
    assert cache.get("b") is None and cache.get("a") == 1 and cache.get("c") == 3
