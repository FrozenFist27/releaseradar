"""End-to-end cycle with a mocked source + notifier: baseline, dedupe, alert."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from radar.config import Config, Settings, YamlConfig
from radar.db import connect
from radar.models import FetchResult, Item


def _cfg(tmp_path):
    return Config(
        settings=Settings(
            RADAR_DB_PATH=str(tmp_path / "radar.db"),
            GITHUB_TOKEN="",
            DISCORD_ALERTS_WEBHOOK_URL="https://discord.example/a",
            DISCORD_HEALTH_WEBHOOK_URL="https://discord.example/h",
        ),
        yaml=YamlConfig(),
    )


def _items():
    now = datetime.now(UTC)
    return [
        Item(
            source="github_releases",
            target="octo/repo",
            item_id="501",
            title="v1",
            url="https://github.com/octo/repo/releases/501",
            published_at=now,
        )
    ]


def test_baseline_first_run_sends_nothing(tmp_path):
    cfg = _cfg(tmp_path)
    with patch("radar.scheduler.GithubReleasesSource") as Src, patch(
        "radar.scheduler.DiscordNotifier"
    ), patch("radar.scheduler.ping_healthchecks", return_value=True):
        instance = Src.return_value
        instance.fetch.return_value = FetchResult(
            target="octo/repo", status="ok", http_status=200, items=_items()
        )
        from radar.scheduler import Scheduler

        s = Scheduler(cfg)
        # Point targets at one repo so the loop has work.
        cfg.yaml.sources.github_releases.targets = ["octo/repo"]
        s.source = instance
        s.run_once()

    conn = connect(cfg.db_path)
    alerts = conn.execute("SELECT COUNT(*) n FROM alerts").fetchone()["n"]
    seen = conn.execute("SELECT COUNT(*) n FROM seen_items").fetchone()["n"]
    conn.close()
    assert seen == 1
    assert alerts == 0  # baseline: no alert on first sight


def test_second_cycle_new_item_alerts(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.yaml.sources.github_releases.targets = ["octo/repo"]
    with patch("radar.scheduler.GithubReleasesSource") as Src, patch(
        "radar.scheduler.DiscordNotifier"
    ), patch("radar.scheduler.ping_healthchecks", return_value=True):
        instance = Src.return_value
        instance.fetch.return_value = FetchResult(
            target="octo/repo", status="ok", http_status=200, items=_items()
        )
        from radar.scheduler import Scheduler

        s = Scheduler(cfg)
        s.source = instance
        s.run_once()  # baseline
        s.run_once()  # still the same items -> still no alert
        # Now a genuinely new item id appears.
        new_item = _items()[0].model_copy(update={"item_id": "502", "title": "v2"})
        instance.fetch.return_value = FetchResult(
            target="octo/repo", status="ok", http_status=200, items=[new_item]
        )
        s.run_once()

    conn = connect(cfg.db_path)
    alerts = conn.execute("SELECT item_key FROM alerts").fetchall()
    conn.close()
    assert [a["item_key"] for a in alerts] == ["github_releases:502"]
