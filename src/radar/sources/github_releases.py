"""GitHub Releases source via the official REST API with ETag caching."""

from __future__ import annotations

from datetime import datetime

import httpx

from ..db import get_etag, set_etag
from ..http import backoff_from_headers, get_with_etag
from ..models import FetchResult, Item

API = "https://api.github.com"


class GithubReleasesSource:
    def __init__(
        self,
        client: httpx.Client,
        conn,
        token: str = "",
        include_prereleases: bool = False,
        per_page: int = 10,
        api_base: str = API,
    ):
        self.api_base = api_base.rstrip("/")
        self.client = client
        self.conn = conn
        self.include_prereleases = include_prereleases
        self.per_page = per_page
        if token:
            self.client.headers["Authorization"] = f"Bearer {token}"
            self.client.headers["X-GitHub-Api-Version"] = "2022-11-28"

    def fetch(self, target: str) -> FetchResult:
        url = f"{self.api_base}/repos/{target}/releases"
        etag = get_etag(self.conn, target)
        out = get_with_etag(self.client, url, etag, params={"per_page": str(self.per_page)})

        if out.status_code == 304:
            return FetchResult(
                target=target,
                status="not_modified",
                http_status=304,
                etag=etag,
                duration_ms=out.duration_ms,
                rate_remaining=_remaining(out.headers),
            )
        if out.status_code in (403, 429):
            return FetchResult(
                target=target,
                status="rate_limited",
                http_status=out.status_code,
                duration_ms=out.duration_ms,
                rate_remaining=_remaining(out.headers),
                error=f"rate limited HTTP {out.status_code}",
                backoff_s=backoff_from_headers(out.headers),
            )
        if out.status_code >= 500:
            return FetchResult(
                target=target,
                status="error",
                http_status=out.status_code,
                duration_ms=out.duration_ms,
                error=f"server error HTTP {out.status_code}",
                backoff_s=60.0,
            )
        if out.status_code != 200:
            return FetchResult(
                target=target,
                status="error",
                http_status=out.status_code,
                duration_ms=out.duration_ms,
                error=f"unexpected HTTP {out.status_code}",
            )

        import json

        raw = json.loads(out.body or b"[]")
        items: list[Item] = []
        for r in raw:
            if r.get("draft"):
                continue
            if r.get("prerelease") and not self.include_prereleases:
                continue
            item = _normalise(target, r)
            if item:
                items.append(item)

        new_etag = out.headers.get("etag") or out.headers.get("ETag")
        if new_etag:
            set_etag(self.conn, target, new_etag)

        return FetchResult(
            target=target,
            status="ok",
            http_status=200,
            items=items,
            etag=new_etag,
            duration_ms=out.duration_ms,
            rate_remaining=_remaining(out.headers),
        )


def _remaining(headers: dict[str, str]) -> int | None:
    for k, v in headers.items():
        if k.lower() == "x-ratelimit-remaining":
            try:
                return int(v)
            except ValueError:
                return None
    return None


def _normalise(target: str, r: dict) -> Item | None:
    try:
        rid = str(r["id"])
        title = (r.get("name") or r.get("tag_name") or "").strip() or "(untitled)"
        url = r.get("html_url") or f"{API}/repos/{target}/releases/{rid}"
        published = r.get("published_at") or r.get("created_at")
        if not published:
            return None
        published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
        author = (r.get("user") or {}).get("login")
        fields = {
            "tag_name": str(r.get("tag_name") or ""),
            "prerelease": str(bool(r.get("prerelease"))),
        }
        body = (r.get("body") or "").strip()
        return Item(
            source="github_releases",
            target=target,
            item_id=rid,
            title=title,
            url=url,
            published_at=published_at,
            author=author,
            fields=fields,
            body_excerpt=body[:1500],
        )
    except Exception:
        return None
