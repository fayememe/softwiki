"""LLM provider circuit breaker.

A dead provider (expired quota, revoked key) must not be treated as thousands of
independent task failures: that fills the queue with noise, churns the database
and hides the real cause. Fatal errors open a breaker; callers fail fast with a
clear reason until the cooldown expires.
"""

from __future__ import annotations

import os
import time

COOLDOWN_SECONDS = float(os.getenv("LLM_BREAKER_COOLDOWN_SECONDS", "900"))
TRANSIENT_STRIKES = int(os.getenv("LLM_BREAKER_TRANSIENT_STRIKES", "3"))
FATAL_HINTS = (
    "预扣费", "余额", "insufficient_quota", "quota", "billing",
    "invalid_api_key", "authentication", "unauthorized", "permission",
)


class ProviderUnavailable(RuntimeError):
    """Raised instead of calling an LLM while the breaker is open."""


def is_fatal(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return True
    text = str(exc).lower()
    return any(hint in text for hint in FATAL_HINTS)


class ProviderBreaker:
    def __init__(self) -> None:
        self.opened_until = 0.0
        self.reason = ""
        self.strikes = 0

    def is_open(self) -> bool:
        return time.monotonic() < self.opened_until

    def open(self, reason: str, seconds: float) -> None:
        self.opened_until = time.monotonic() + max(1.0, seconds)
        self.reason = reason[:300]

    def record_failure(self, exc: BaseException) -> None:
        if is_fatal(exc):
            # Fatal errors never succeed on retry: stop everything immediately.
            self.open(f"provider rejected requests: {exc}", COOLDOWN_SECONDS)
            self.strikes = TRANSIENT_STRIKES
            return
        self.strikes += 1
        if self.strikes >= TRANSIENT_STRIKES:
            self.open(f"provider failing repeatedly: {exc}", 60)

    def record_success(self) -> None:
        self.strikes = 0
        self.opened_until = 0.0
        self.reason = ""

    def status(self) -> dict:
        remaining = max(0.0, self.opened_until - time.monotonic())
        return {
            "open": remaining > 0,
            "reason": self.reason if remaining > 0 else "",
            "retry_in_seconds": round(remaining, 1),
            "strikes": self.strikes,
        }


breaker = ProviderBreaker()
