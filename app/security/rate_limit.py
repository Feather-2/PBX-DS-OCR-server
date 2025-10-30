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
        self._stop_event = threading.Event()

        # 后台清理线程，减少主线程的清理开销
        self._cleanup_thread = threading.Thread(target=self._periodic_cleanup, name="rate-limiter-cleanup", daemon=True)
        self._cleanup_thread.start()

    def _periodic_cleanup(self):
        """后台线程：定期清理过期的 bucket"""
        while not self._stop_event.is_set():
            try:
                time.sleep(60)  # 每分钟清理一次
                now = time.monotonic()
                cutoff = now - self._ttl
                with self._lock:
                    to_del = [k for k, (_, last) in self._buckets.items() if last < cutoff]
                    for k in to_del:
                        self._buckets.pop(k, None)
                    self._last_cleanup = now
            except Exception:
                # 清理失败不影响主流程
                pass

    def _cleanup(self, now: float) -> None:
        """同步清理（仅在高频调用时使用，避免后台线程延迟）"""
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
            # 定期清理（作为后台线程的补充）
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

    def stop(self):
        """停止后台清理线程"""
        self._stop_event.set()
        if self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=1.0)

