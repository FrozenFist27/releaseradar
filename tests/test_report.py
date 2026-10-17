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
