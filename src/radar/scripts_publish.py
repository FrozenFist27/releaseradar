"""Publish a synthetic release in the sandbox repo (latency harness)."""

from __future__ import annotations

import httpx

API = "https://api.github.com"


def publish_release(client: httpx.Client, repo: str, token: str, tag: str) -> dict:
    """Create a release with the given tag. Returns the release JSON."""
    client.headers["Authorization"] = f"Bearer {token}"
    client.headers["X-GitHub-Api-Version"] = "2022-11-28"
    client.headers["Accept"] = "application/vnd.github+json"
    url = f"{API}/repos/{repo}/releases"
    payload = {
        "tag_name": tag,
        "name": f"ReleaseRadar latency test {tag}",
        "body": "Synthetic release published by the ReleaseRadar latency harness.",
        "draft": False,
        "prerelease": False,
    }
    r = client.post(url, json=payload)
    r.raise_for_status()
    return r.json()


def delete_release(client: httpx.Client, repo: str, token: str, release_id: int) -> None:
    client.headers["Authorization"] = f"Bearer {token}"
    client.headers["X-GitHub-Api-Version"] = "2022-11-28"
    url = f"{API}/repos/{repo}/releases/{release_id}"
    r = client.delete(url)
    r.raise_for_status()
