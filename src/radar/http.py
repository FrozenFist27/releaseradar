"""httpx client with a User-Agent, ETag support and a rate-limit guard."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

USER_AGENT = "ReleaseRadar/0.1 (+https://github.com/releaseradar)"


@dataclass
class HttpOutcome:
    status_code: int
    headers: dict[str, str]
    body: bytes | None
    duration_ms: int
    from_cache: bool = False  # True when a 304 short-circuits


class RateLimiter:
    """Track GitHub's primary rate limit and honour X-RateLimit-Remaining."""

    def __init__(self) -> None:
        self.remaining: int | None = None
        self.reset_at: float | None = None
        self.retry_after: float | None = None

    def observe(self, headers: httpx.Headers) -> None:
        rem = headers.get("x-ratelimit-remaining")
        if rem is not None and rem.isdigit():
            self.remaining = int(rem)
        reset = headers.get("x-ratelimit-reset")
        if reset is not None and reset.isdigit():
            self.reset_at = float(reset)
        ra = headers.get("retry-after")
        if ra is not None and ra.isdigit():
            self.retry_after = float(ra)

    def should_backoff(self) -> bool:
        if self.remaining is not None and self.remaining <= 0:
            return True
        if self.retry_after is not None and self.retry_after > 0:
            return True
        return False

    def backoff_seconds(self, cap: float = 300.0) -> float:
        now = time.time()
        cands: list[float] = []
        if self.retry_after:
            cands.append(self.retry_after)
        if self.reset_at and self.reset_at > now:
            cands.append(min(self.reset_at - now, cap))
        return min(max(cands, default=cap), cap)


def backoff_from_headers(headers: dict[str, str], default: float = 60.0, cap: float = 300.0) -> float:
    """Seconds to wait after a 403/429: Retry-After, else primary-limit reset, else default."""
    rl = RateLimiter()
    rl.observe(httpx.Headers(headers))
    if rl.retry_after:
        return min(rl.retry_after, cap)
    if rl.remaining is not None and rl.remaining <= 0 and rl.reset_at:
        return max(1.0, min(rl.reset_at - time.time(), cap))
    return default


def build_client(timeout: float = 20.0) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
        timeout=timeout,
        follow_redirects=True,
    )


def get_with_etag(
    client: httpx.Client,
    url: str,
    etag: str | None,
    params: dict[str, str] | None = None,
) -> HttpOutcome:
    """GET with conditional If-None-Match. 304 responses return body=None."""
    headers: dict[str, str] = {}
    if etag:
        headers["If-None-Match"] = etag
    start = time.perf_counter()
    resp = client.get(url, params=params, headers=headers)
    dur = int((time.perf_counter() - start) * 1000)
    body: bytes | None = None if resp.status_code == 304 else resp.content
    return HttpOutcome(
        status_code=resp.status_code,
        headers=dict(resp.headers),
        body=body,
        duration_ms=dur,
        from_cache=resp.status_code == 304,
    )
