"""Report: percentile + aggregation from a seeded DB."""

from __future__ import annotations

from datetime import UTC, datetime

from radar.db import connect, insert_alert, record_check
from radar.models import AlertRecord, CheckResult
from radar.report import _percentile, compute_report


def test_percentile():
    vals = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert _percentile(vals, 0.5) == 30.0
    assert _percentile(vals, 0.0) == 10.0
    assert _percentile(vals, 1.0) == 50.0
    assert _percentile([], 0.5) == 0.0
    assert _percentile([7.0], 0.9) == 7.0


def test_compute_report_from_seeded_db(tmp_path):
    db = tmp_path / "radar.db"
    conn = connect(db)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(8):
        record_check(
            conn,
            CheckResult(
                cycle_id=f"c{i}",
                target="octo/repo",
                started_at=base,
                duration_ms=100,
                status="ok" if i < 7 else "error",
                http_status=200,
            ),
        )
    for i, lat in enumerate([5.0, 15.0, 25.0]):
        insert_alert(
            conn,
            AlertRecord(
                item_key=f"github_releases:{i}",
                channel="discord",
                published_at=base,
                detected_at=base,
                alerted_at=base,
                latency_s=lat,
                http_status=204,
            ),
        )
    conn.commit()
    conn.close()

    r = compute_report(db)
    assert r["total_checks"] == 8
    assert r["ok_checks"] == 7
    assert r["error_checks"] == 1
    assert r["alerts_count"] == 3
    assert r["latency"]["n"] == 3
    assert r["latency"]["p50_s"] == 15.0
    assert r["latency"]["max_s"] == 25.0
    assert r["uptime_pct"] == 87.5


def test_log_audit_detects_duplicate_posts(tmp_path):
    from radar.report import audit_duplicate_posts

    assert audit_duplicate_posts(tmp_path) is None
    (tmp_path / "radar-2026-01-01.jsonl").write_text(
        '{"event": "alert_sent", "item_key": "a"}\n'
        '{"event": "alert_sent", "item_key": "b"}\n'
        '{"event": "alert_sent", "item_key": "a"}\n'
        '{"event": "check"}\n',
        encoding="utf-8",
    )
    assert audit_duplicate_posts(tmp_path) == 1


def test_cycle_stats_max_gap(tmp_path):
    from datetime import timedelta

    conn = connect(tmp_path / "r.db")
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    for i, off in enumerate([0, 30, 60, 560]):
        record_check(conn, CheckResult(cycle_id=f"c{i}", target="x", started_at=t0 + timedelta(seconds=off),
                                       duration_ms=1, status="ok"))
    conn.commit()
    conn.close()
    r = compute_report(tmp_path / "r.db")
    assert r["cycles"] == 4 and r["max_gap_s"] == 500.0 and r["gaps_over_120s"] == 1
