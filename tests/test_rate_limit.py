"""Rate-limit backoff behaviour."""

from __future__ import annotations

import time

import httpx

from radar.http import RateLimiter


def _headers(d):
    return httpx.Headers(d)


def test_remaining_zero_triggers_backoff():
    rl = RateLimiter()
    rl.observe(_headers({"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(time.time()) + 60)}))
    assert rl.should_backoff()
    b = rl.backoff_seconds()
    assert 0 < b <= 60


def test_retry_after_honoured():
    rl = RateLimiter()
    rl.observe(_headers({"retry-after": "42"}))
    assert rl.should_backoff()
    assert rl.backoff_seconds() == 42


def test_no_backoff_when_remaining_positive():
    rl = RateLimiter()
    rl.observe(_headers({"x-ratelimit-remaining": "4000"}))
    assert not rl.should_backoff()


def test_backoff_capped_at_cap():
    rl = RateLimiter()
    rl.observe(_headers({"retry-after": "9999"}))
    assert rl.backoff_seconds(cap=300) == 300
