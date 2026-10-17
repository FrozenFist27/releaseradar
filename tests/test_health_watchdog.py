"""Watchdog: alert at threshold, no repeat, recovery."""

from __future__ import annotations

import datetime as dt

from radar.health import Watchdog


def test_no_alert_before_threshold():
    wd = Watchdog(fail_alert_after_s=300)
    wd.failing_since = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=299)
    assert wd.record_failure("boom", "t") == []


def test_alert_at_threshold():
    wd = Watchdog(fail_alert_after_s=300)
    wd.failing_since = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=301)
    events = wd.record_failure("boom", "t")
    assert len(events) == 1
    assert events[0].startswith("failure:")


def test_no_repeat_within_rearm():
    wd = Watchdog(fail_alert_after_s=300, rearm_interval_s=1800)
    wd.failing_since = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=400)
    assert len(wd.record_failure("boom", "t")) == 1
    # Immediate second failure: no repeat.
    assert wd.record_failure("boom", "t") == []


def test_recovery_after_alert():
    wd = Watchdog(fail_alert_after_s=300)
    wd.failing_since = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=400)
    assert len(wd.record_failure("boom", "t")) == 1
    events = wd.record_success()
    assert events == ["recovery"]
    assert wd.alerted is False
    assert wd.failing_since is None
