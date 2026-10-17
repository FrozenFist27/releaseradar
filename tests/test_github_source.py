"""GitHub source: parsing, draft/prerelease skipping, ETag/304."""

from __future__ import annotations

import json as _json
from pathlib import Path as _Path

import httpx
import respx

from radar.db import connect
from radar.sources.github_releases import GithubReleasesSource

_FIX = _Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return _json.loads((_FIX / name).read_text(encoding="utf-8"))


@respx.mock
def test_parses_and_skips_drafts_and_prereleases(tmp_path):
    conn = connect(tmp_path / "radar.db")
    respx.get("https://api.github.com/repos/octo/repo/releases").mock(
        return_value=httpx.Response(
            200,
            json=load_fixture("github_releases_page1.json"),
            headers={"ETag": 'W/"abc123"', "X-RateLimit-Remaining": "4999"},
        )
    )
    with httpx.Client() as client:
        src = GithubReleasesSource(client, conn, token="t", include_prereleases=False)
        fr = src.fetch("octo/repo")
    conn.close()
    assert fr.status == "ok"
    ids = [i.item_id for i in fr.items]
    assert ids == ["101", "102"]  # draft 104 and prerelease 103 skipped
    assert fr.etag == 'W/"abc123"'
    assert fr.rate_remaining == 4999


@respx.mock
def test_include_prereleases_toggle(tmp_path):
    conn = connect(tmp_path / "radar.db")
    respx.get("https://api.github.com/repos/octo/repo/releases").mock(
        return_value=httpx.Response(200, json=load_fixture("github_releases_page1.json"))
    )
    with httpx.Client() as client:
        src = GithubReleasesSource(client, conn, token="t", include_prereleases=True)
        fr = src.fetch("octo/repo")
    conn.close()
    ids = [i.item_id for i in fr.items]
    assert "103" in ids  # prerelease now included
    assert "104" not in ids  # draft still skipped


@respx.mock
def test_304_not_modified(tmp_path):
    conn = connect(tmp_path / "radar.db")
    # Seed the etag cache first.
    from radar.db import set_etag

    set_etag(conn, "octo/repo", 'W/"abc123"')
    conn.commit()
    respx.get("https://api.github.com/repos/octo/repo/releases").mock(
        return_value=httpx.Response(304)
    )
    with httpx.Client() as client:
        src = GithubReleasesSource(client, conn, token="t")
        fr = src.fetch("octo/repo")
    conn.close()
    assert fr.status == "not_modified"
    assert fr.http_status == 304
    assert fr.items == []


@respx.mock
def test_sends_if_none_match_header(tmp_path):
    conn = connect(tmp_path / "radar.db")
    from radar.db import set_etag

    set_etag(conn, "octo/repo", 'W/"xyz"')
    conn.commit()
    route = respx.get("https://api.github.com/repos/octo/repo/releases").mock(
        return_value=httpx.Response(304)
    )
    with httpx.Client() as client:
        src = GithubReleasesSource(client, conn, token="t")
        src.fetch("octo/repo")
    conn.close()
    assert route.calls[0].request.headers.get("If-None-Match") == 'W/"xyz"'
