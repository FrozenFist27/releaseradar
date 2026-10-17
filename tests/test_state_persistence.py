"""State must survive between one-shot runs (systemd timer drives `radar once`)."""

from __future__ import annotations

import datetime as dt
import json
import time
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
import respx

from radar.config import Config, Settings, YamlConfig
from radar.db import connect, get_kv, set_kv
from radar.http import backoff_from_headers
from radar.models import FetchResult, Item


def _cfg(tmp_path, **yaml):
    c = Config(
        settings=Settings(
            RADAR_DB_PATH=str(tmp_path / "radar.db"),
            DISCORD_ALERTS_WEBHOOK_URL="https://discord.example/a",
            DISCORD_HEALTH_WEBHOOK_URL="https://discord.example/h",
        ),
        yaml=YamlConfig(**yaml),
    )
    c.yaml.sources.github_releases.targets = ["octo/repo"]
    return c


def _item(i="1"):
    return Item(
        source="github_releases", target="octo/repo", item_id=i, title="t",
        url="https://github.com/octo/repo/releases/1", published_at=datetime.now(UTC),
    )


def _run(cfg, fetch_result=None, exc=None):
    from radar.scheduler import Scheduler

    with patch("radar.scheduler.GithubReleasesSource") as Src, patch(
        "radar.scheduler.DiscordNotifier"
    ) as Notif, patch("radar.scheduler.ping_healthchecks", return_value=True) as ping:
        inst = Src.return_value
        if exc:
            inst.fetch.side_effect = exc
        else:
            inst.fetch.return_value = fetch_result
        s = Scheduler(cfg)  # a NEW scheduler each time == a new process
        s.source = inst
        s.run_once()
        return Notif.return_value, ping


def test_watchdog_alert_fires_across_separate_runs(tmp_path):
    cfg = _cfg(tmp_path)
    notif, _ = _run(cfg, exc=RuntimeError("down"))
    # Pretend the outage started 6 minutes ago (persisted state), then run again.
    conn = connect(cfg.db_path)
    set_kv(
        conn, "watchdog",
        json.dumps({"failing_since": (datetime.now(UTC) - dt.timedelta(minutes=6)).isoformat(),
                    "last_alert_at": None, "alerted": False}),
    )
    conn.commit()
    conn.close()
    notif, _ = _run(cfg, exc=RuntimeError("down"))
    texts = [c.args[0] for c in notif.send_text.call_args_list]
    assert any("@here" in t for t in texts)
    # A third run must NOT repeat the loud alert.
    notif, _ = _run(cfg, exc=RuntimeError("down"))
    assert not any("@here" in c.args[0] for c in notif.send_text.call_args_list)


def test_recovery_message_after_alert_and_ping_only_on_success(tmp_path):
    cfg = _cfg(tmp_path)
    _run(cfg, exc=RuntimeError("down"))
    conn = connect(cfg.db_path)
    set_kv(
        conn, "watchdog",
        json.dumps({"failing_since": (datetime.now(UTC) - dt.timedelta(minutes=8)).isoformat(),
                    "last_alert_at": time.time(), "alerted": True}),
    )
    conn.commit()
    conn.close()
    ok = FetchResult(target="octo/repo", status="ok", http_status=200, items=[_item()])
    notif, ping = _run(cfg, fetch_result=ok)
    assert ping.called
    assert any("recovered after 8" in c.args[0] for c in notif.send_text.call_args_list)
    conn = connect(cfg.db_path)
    assert '"alerted": false' in get_kv(conn, "watchdog")
    conn.close()


def test_no_ping_when_check_fails(tmp_path):
    cfg = _cfg(tmp_path)
    _, ping = _run(cfg, exc=RuntimeError("down"))
    assert not ping.called


def test_rate_limited_sets_backoff_and_skips_next_run(tmp_path):
    cfg = _cfg(tmp_path)
    rl = FetchResult(
        target="octo/repo", status="rate_limited", http_status=429, error="rl", backoff_s=120.0
    )
    _run(cfg, fetch_result=rl)
    conn = connect(cfg.db_path)
    assert float(get_kv(conn, "backoff_until:octo/repo")) > time.time() + 100
    conn.close()
    from radar.scheduler import Scheduler

    with patch("radar.scheduler.GithubReleasesSource") as Src, patch(
        "radar.scheduler.DiscordNotifier"
    ), patch("radar.scheduler.ping_healthchecks", return_value=True):
        inst = Src.return_value
        s = Scheduler(cfg)
        s.source = inst
        s.run_once()
        assert not inst.fetch.called  # honoured the backoff window


def test_backoff_from_headers():
    assert backoff_from_headers({"retry-after": "42"}) == 42
    assert backoff_from_headers({"retry-after": "9999"}) == 300
    reset = str(int(time.time()) + 90)
    b = backoff_from_headers({"x-ratelimit-remaining": "0", "x-ratelimit-reset": reset})
    assert 60 < b <= 91
    assert backoff_from_headers({}) == 60


@respx.mock
def test_source_429_carries_backoff():
    from radar.sources.github_releases import GithubReleasesSource

    respx.get("https://api.github.com/repos/o/r/releases").mock(
        return_value=httpx.Response(429, headers={"retry-after": "77"})
    )
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = None
    src = GithubReleasesSource(httpx.Client(), conn)
    fr = src.fetch("o/r")
    assert fr.status == "rate_limited" and fr.backoff_s == 77


def test_detected_at_is_before_alerted_at(tmp_path):
    cfg = _cfg(tmp_path)
    ok = FetchResult(target="octo/repo", status="ok", http_status=200, items=[_item("1")])
    _run(cfg, fetch_result=ok)  # baseline
    ok2 = FetchResult(target="octo/repo", status="ok", http_status=200, items=[_item("2")])
    _run(cfg, fetch_result=ok2)
    conn = connect(cfg.db_path)
    row = conn.execute("SELECT detected_at, alerted_at FROM alerts").fetchone()
    conn.close()
    assert row["detected_at"] <= row["alerted_at"]


def test_heartbeat_clock_persisted_and_fires(tmp_path):
    cfg = _cfg(tmp_path, heartbeat_interval_s=60)
    ok = FetchResult(target="octo/repo", status="ok", http_status=200, items=[])
    notif, _ = _run(cfg, fetch_result=ok)
    assert not notif.send_text.called  # first run only starts the clock
    conn = connect(cfg.db_path)
    set_kv(conn, "last_heartbeat", (datetime.now(UTC) - dt.timedelta(minutes=5)).isoformat())
    conn.commit()
    conn.close()
    notif, _ = _run(cfg, fetch_result=ok)
    assert any("alive" in c.args[0] for c in notif.send_text.call_args_list)
