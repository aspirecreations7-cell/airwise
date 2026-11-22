"""Small in-memory abuse protection: a per-client rate limit and a daily LLM budget."""
import time
from collections import defaultdict, deque


class RateLimiter:
    """Sliding-window limiter keyed by client id."""

    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self.max_calls = max_calls
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        """Record a call and return True if the client is still within its limit."""
        now = time.monotonic() if now is None else now
        if len(self._hits) > 10_000:
            self._hits.clear()
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.max_calls:
            return False
        hits.append(now)
        return True


class DailyBudget:
    """Caps paid LLM calls per day. The counter resets when the date changes."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._day = ""
        self._used = 0

    def take(self, today: str) -> bool:
        """Use one call from today's budget. Returns False when it is exhausted."""
        if today != self._day:
            self._day, self._used = today, 0
        if self._used >= self.limit:
            return False
        self._used += 1
        return True
