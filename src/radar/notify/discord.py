"""Discord webhook notifier (embeds + plain text)."""

from __future__ import annotations

import time

import httpx

from ..models import FilterDecision, Item

MAX_RETRY_AFTER = 30.0


class DiscordNotifier:
    def __init__(self, client: httpx.Client, webhook_url: str, username: str = "ReleaseRadar"):
        self.client = client
        self.webhook_url = webhook_url
        self.username = username

    def _post(self, payload: dict) -> int:
        delay = 0.5
        for _attempt in range(3):
            resp = self.client.post(self.webhook_url, json=payload)
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("retry-after", delay))
                time.sleep(min(retry_after, MAX_RETRY_AFTER))
                delay = min(delay * 2, MAX_RETRY_AFTER)
                continue
            resp.raise_for_status()
            return resp.status_code
        resp.raise_for_status()
        return resp.status_code

    def send_item(self, item: Item, decision: FilterDecision | None = None) -> int:
        fields = [
            {"name": "Published (UTC)", "value": item.published_at.isoformat(), "inline": True},
            {"name": "Target", "value": item.target, "inline": True},
        ]
        if item.author:
            fields.append({"name": "Author", "value": item.author, "inline": True})
        tag = item.fields.get("tag_name")
        if tag:
            fields.append({"name": "Tag", "value": tag, "inline": True})
        fields.append(
            {"name": "Pre-release", "value": item.fields.get("prerelease", "False"), "inline": True}
        )
        if decision and decision.summary:
            fields.append({"name": "Summary", "value": decision.summary[:1024], "inline": False})

        embed = {
            "title": f"[{item.target}] {item.title}"[:256],
            "url": str(item.url),
            "fields": fields[:25],
            "footer": {"text": f"item {item.key} • ReleaseRadar"},
        }
        payload = {"username": self.username, "embeds": [embed]}
        return self._post(payload)

    def send_text(self, content: str) -> int:
        return self._post({"username": self.username, "content": content[:2000]})
