"""A small bounded cache with time-based expiry."""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Generic, TypeVar

V = TypeVar("V")


class TTLCache(Generic[V]):
    """Least-recently-used cache whose entries expire after ``ttl_s`` seconds."""

    def __init__(
        self, max_size: int, ttl_s: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._max_size, self._ttl_s, self._clock = max_size, ttl_s, clock
        self._items: OrderedDict[str, tuple[float, V]] = OrderedDict()

    def get(self, key: str) -> V | None:
        """Returns the cached value, or None if missing or expired."""
        hit = self._items.get(key)
        if hit is None or self._clock() - hit[0] > self._ttl_s:
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return hit[1]

    def put(self, key: str, value: V) -> None:
        """Stores a value, evicting the least recently used entry when full."""
        self._items[key] = (self._clock(), value)
        self._items.move_to_end(key)
        while len(self._items) > self._max_size:
            self._items.popitem(last=False)

    def __len__(self) -> int:
        """Returns the number of stored entries, expired ones included until read."""
        return len(self._items)
