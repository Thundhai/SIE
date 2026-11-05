"""Rate limiting abstraction — Intelligence Platform Integration &
Enterprise API v0.1, item 13 (implementation in `item 44`'s own
numbering; this module is what both refer to).

    RateLimiter (Protocol)
        .check(key, *, limit, window_seconds) -> RateLimitResult
        LocalRateLimiter   -- in-memory, per-process, fixed-window
        (RedisRateLimiter   -- documented extension point, not implemented)

**A simple in-memory implementation is the foundation, explicitly not
suitable for a multi-instance production deployment** (item 13's own
instruction) — `LocalRateLimiter` counts requests in this one process's
memory, so a deployment running N replicas behind a load balancer gets
each replica enforcing its own independent limit (an effective limit of
`N * configured_limit`, and a client's count resets whenever a request
happens to land on a different replica). This is documented here, in the
README, and in the final report — never silently presented as
production-grade multi-instance rate limiting.

**The interface is what carries forward**, not this implementation — a
`RedisRateLimiter` (or any shared-state backend) implementing the same
`RateLimiter` protocol is a drop-in replacement for
`get_rate_limiter()` below; nothing about the dependency
(`app/api/deps_rate_limit.py`) or any call site would need to change.

**Tenant-aware, per-client, read/write distinguished** — the `key` a
caller builds (see `app/api/deps_rate_limit.py`) already encodes the
calling identity (a machine client's own `client_id`, or a human's
`user_id`) plus which limit class applies (`read` vs `write`); this
module itself is deliberately generic over what `key` even means, so it
never needs to know about organizations, scopes, or HTTP at all.
"""

from __future__ import annotations

import heapq
import threading
import time
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: float  # seconds until the current window resets


class RateLimiter(Protocol):
    def check(self, key: str, *, limit: int, window_seconds: float) -> RateLimitResult: ...


class LocalRateLimiter:
    """Fixed-window counter, keyed by `key`, held in a plain `dict` behind
    one lock. Fixed-window (not sliding/token-bucket) is a deliberate
    simplicity choice for this foundation — it allows a short burst right
    at a window boundary, a known, accepted imprecision of the simplest
    correct rate-limiting algorithm; nothing in this milestone claims
    exact request-spacing guarantees.
    """

    #: Expired windows are swept every this many checks, so keys from
    #: one-off callers (e.g. distinct client IPs on a public endpoint)
    #: don't accumulate forever. The sweep only ever drops expired windows.
    PRUNE_EVERY = 1024
    #: Hard bound on tracked keys. Only admitting a NEW key at the cap makes
    #: room: expired windows go first, then the oldest live windows, in one
    #: batch. A key being checked is therefore never evicted to make room
    #: for itself, so a client that is being refused cannot reset its own
    #: counter by calling again.
    MAX_KEYS = 50_000
    #: How many live windows one eviction drops (5% of the cap), so a flood
    #: of new keys pays for one scan per batch, not one per request.
    EVICT_BATCH = 2_500

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key -> (window_start_monotonic, count, window_seconds)
        self._windows: dict[str, tuple[float, int, float]] = {}
        self._checks = 0

    def check(self, key: str, *, limit: int, window_seconds: float) -> RateLimitResult:
        now = time.monotonic()
        with self._lock:
            self._checks += 1
            if self._checks % self.PRUNE_EVERY == 0:
                self._drop_expired(now)

            entry = self._windows.get(key)
            if entry is None and len(self._windows) >= self.MAX_KEYS:
                self._make_room(now)

            window_start, count, _ = entry if entry is not None else (now, 0, window_seconds)
            if now - window_start >= window_seconds:
                window_start, count = now, 0

            count += 1
            self._windows[key] = (window_start, count, window_seconds)

            allowed = count <= limit
            remaining = max(0, limit - count)
            reset_seconds = max(0.0, window_seconds - (now - window_start))
            return RateLimitResult(allowed=allowed, limit=limit, remaining=remaining, reset_seconds=reset_seconds)

    def _drop_expired(self, now: float) -> None:
        self._windows = {k: v for k, v in self._windows.items() if now - v[0] < v[2]}

    def _make_room(self, now: float) -> None:
        """Called only before admitting a key that is not tracked."""
        self._drop_expired(now)
        overflow = len(self._windows) - self.MAX_KEYS + 1
        if overflow > 0:
            count = max(overflow, min(self.EVICT_BATCH, len(self._windows)))
            for k, _ in heapq.nsmallest(count, self._windows.items(), key=lambda item: item[1][0]):
                del self._windows[k]

    def tracked_keys(self) -> int:
        """How many keys are currently tracked (tests and diagnostics)."""
        with self._lock:
            return len(self._windows)

    def reset(self) -> None:
        """Test-only convenience — clears all counters. Never called from
        application code."""
        with self._lock:
            self._windows.clear()


_local_rate_limiter = LocalRateLimiter()


def get_rate_limiter() -> RateLimiter:
    """The one seam a future `RedisRateLimiter` (or any shared-state
    implementation) replaces — see module docstring. A single
    process-wide `LocalRateLimiter` instance today."""
    return _local_rate_limiter
