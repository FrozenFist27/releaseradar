"""Discord notifier: payload shape, 429 retry, pending on failure."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import respx

from radar.db import enqueue_pending, insert_alert, list_pending
from radar.models import AlertRecord, Item
from radar.notify.discord import DiscordNotifier

WEBHOOK = "https://example.invalid/webhook/123/token"


def _item():
    return Item(
        source="github_releases",
        target="octo/repo",
        item_id="201",
        title="v2.0.0",
        url="https://github.com/octo/repo/releases/201",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        fields={"tag_name": "v2.0.0"},
    )


@respx.mock
def test_payload_shape():
    route = respx.post(WEBHOOK).mock(return_value=httpx.Response(204))
    with httpx.Client() as c:
        n = DiscordNotifier(c, WEBHOOK)
        n.send_item(_item())
    body = route.calls[0].request.content
    assert b"embeds" in body
    assert b"octo/repo" in body
    assert b"item github_releases:201" in body


@respx.mock
def test_429_retry_then_success():
    respx.post(WEBHOOK).mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(204),
        ]
    )
    with httpx.Client() as c:
        n = DiscordNotifier(c, WEBHOOK)
        status = n.send_item(_item())
    assert status == 204


def test_failure_queues_pending(tmp_db):
    # Simulate: alert insert guard + pending queue.
    item = _item()
    enqueue_pending(tmp_db, item.key, item.model_dump_json())
    tmp_db.commit()
    rows = list_pending(tmp_db)
    assert len(rows) == 1
    assert rows[0]["item_key"] == item.key


def test_alert_insert_is_idempotent(tmp_db):
    rec = AlertRecord(
        item_key="github_releases:201",
        channel="discord",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        detected_at=datetime(2026, 1, 1, tzinfo=UTC),
        alerted_at=datetime(2026, 1, 1, tzinfo=UTC),
        latency_s=10.0,
        http_status=204,
    )
    assert insert_alert(tmp_db, rec) is True
    tmp_db.commit()
    assert insert_alert(tmp_db, rec) is False  # duplicate blocked by PK
    tmp_db.commit()
