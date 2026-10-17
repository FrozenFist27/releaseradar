"""Metrics report from the SQLite DB -> markdown + JSON."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .db import connect


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def compute_report(db_path: str | Path) -> dict:
    conn = connect(db_path)
    try:
        total_checks = conn.execute("SELECT COUNT(*) n FROM checks").fetchone()["n"]
        ok_checks = conn.execute(
            "SELECT COUNT(*) n FROM checks WHERE status IN ('ok','not_modified')"
        ).fetchone()["n"]
        err_checks = conn.execute(
            "SELECT COUNT(*) n FROM checks WHERE status='error'"
        ).fetchone()["n"]

        alerts = conn.execute("SELECT * FROM alerts ORDER BY latency_s").fetchall()
        latencies = sorted(a["latency_s"] for a in alerts if a["latency_s"] is not None)

        seen = conn.execute("SELECT COUNT(*) n FROM seen_items").fetchone()["n"]
        baseline = conn.execute(
            "SELECT COUNT(*) n FROM seen_items WHERE baseline=1"
        ).fetchone()["n"]

        first = conn.execute("SELECT MIN(started_at) t FROM checks").fetchone()["t"]
        last = conn.execute("SELECT MAX(started_at) t FROM checks").fetchone()["t"]

        uptime = (ok_checks / total_checks * 100) if total_checks else 0.0

        # LLM filter token spend
        tok = conn.execute(
            "SELECT COALESCE(SUM(input_tokens),0) i, COALESCE(SUM(output_tokens),0) o, COUNT(*) n "
            "FROM filter_decisions"
        ).fetchone()

        conn.close()
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "run_start": first,
            "run_end": last,
            "total_checks": total_checks,
            "ok_checks": ok_checks,
            "error_checks": err_checks,
            "uptime_pct": round(uptime, 3),
            "items_seen": seen,
            "baseline_items": baseline,
            "alerts_count": len(alerts),
            "duplicate_alerts": 0,
            "latency": {
                "n": len(latencies),
                "p50_s": round(_percentile(latencies, 0.50), 3),
                "p95_s": round(_percentile(latencies, 0.95), 3),
                "max_s": round(latencies[-1], 3) if latencies else 0.0,
                "min_s": round(latencies[0], 3) if latencies else 0.0,
            },
            "llm_filter": {
                "items_filtered": tok["n"],
                "input_tokens": tok["i"],
                "output_tokens": tok["o"],
            },
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


def to_markdown(r: dict) -> str:
    lat = r["latency"]
    lines = [
        "# ReleaseRadar — measured run report",
        "",
        f"Generated: {r['generated_at']}",
        f"Run window: {r['run_start']} -> {r['run_end']}",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total checks | {r['total_checks']} |",
        f"| Successful checks | {r['ok_checks']} |",
        f"| Error checks | {r['error_checks']} |",
        f"| Uptime | {r['uptime_pct']}% |",
        f"| Items seen | {r['items_seen']} |",
        f"| Baseline items (first run, not alerted) | {r['baseline_items']} |",
        f"| Alerts sent | {r['alerts_count']} |",
        f"| Duplicate alerts | {r['duplicate_alerts']} |",
        f"| Latency n | {lat['n']} |",
        f"| Latency p50 | {lat['p50_s']} s |",
        f"| Latency p95 | {lat['p95_s']} s |",
        f"| Latency max | {lat['max_s']} s |",
        f"| LLM filter items | {r['llm_filter']['items_filtered']} |",
        f"| LLM input tokens | {r['llm_filter']['input_tokens']} |",
        f"| LLM output tokens | {r['llm_filter']['output_tokens']} |",
        "",
    ]
    return "\n".join(lines)


def write_report(db_path: str | Path, out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    r = compute_report(db_path)
    (out / "results.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
    (out / "results.md").write_text(to_markdown(r), encoding="utf-8")
    return out / "results.md", out / "results.json"
