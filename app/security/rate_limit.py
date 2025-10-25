from __future__ import annotations

import time
import threading
from typing import Dict

class RateLimiter:
    def __init__(self, rate_per_sec: float, burst: int, ttl_seconds: int = 300) -> None:
        self.rate = max(0.1, float(rate_per_sec))
        self.burst = max(1, int(burst))
        self._buckets: Dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()
        self._ttl = max(60, int(ttl_seconds))

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < 60:
            return
        cutoff = now - self._ttl
        to_del = []
        for key, (_, last) in self._buckets.items():
            if last < cutoff:
                to_del.append(key)
        for k in to_del:
            self._buckets.pop(k, None)
        self._last_cleanup = now

    def allow(self, key: str, tokens: float = 1.0) -> bool:
        now = time.monotonic()
        with self._lock:
            self._cleanup(now)
            tok, last = self._buckets.get(key, (float(self.burst), now))
            # refill
            elapsed = max(0.0, now - last)
            tok = min(float(self.burst), tok + self.rate * elapsed)
            if tok >= tokens:
                tok -= tokens
                self._buckets[key] = (tok, now)
                return True
            else:
                self._buckets[key] = (tok, now)
                return False

