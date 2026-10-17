"""Typer CLI: run, once, report, init-db, simulate-outage, publish-test-release."""

from __future__ import annotations

import signal
import sys
import time

import typer

from .config import load_config
from .db import connect, db_session
from .health import record_health_event
from .logging_setup import setup_logging
from .report import compute_report, to_markdown, write_report

app = typer.Typer(help="ReleaseRadar — monitor-and-alert with zero duplicates.", no_args_is_help=True)


@app.command()
def init_db(config: str = typer.Option(None, help="Path to config.yaml")):
    """Create the SQLite schema."""
    cfg = load_config(config)
    connect(cfg.db_path)
    typer.echo(f"Initialized DB at {cfg.db_path}")


@app.command()
def once(config: str = typer.Option(None)):
    """Run a single poll cycle then exit."""
    cfg = load_config(config)
    setup_logging()
    from .scheduler import Scheduler

    s = Scheduler(cfg)
    s.run_once()
    s.shutdown()


@app.command()
def run(config: str = typer.Option(None)):
    """Run the poll loop until interrupted (SIGTERM/SIGINT graceful)."""
    cfg = load_config(config)
    setup_logging()
    from .scheduler import Scheduler

    s = Scheduler(cfg)

    def _graceful(signum, frame):
        typer.echo("Shutting down...")
        s.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)
    with db_session(cfg.db_path) as conn:
        record_health_event(conn, "startup", "scheduler starting")
    s.run_forever()


@app.command()
def report(
    config: str = typer.Option(None),
    out: str = typer.Option("docs", help="Output directory"),
    as_json: bool = typer.Option(False, "--json", help="Print JSON only"),
    log_dir: str = typer.Option("data/logs", help="JSONL logs for the duplicate audit"),
):
    """Compute metrics from the DB and write docs/results.{md,json}."""
    cfg = load_config(config)
    r = compute_report(cfg.db_path, log_dir)
    if as_json:
        import json as _json

        typer.echo(_json.dumps(r, indent=2))
        return
    write_report(cfg.db_path, out, log_dir)
    typer.echo(to_markdown(r))


@app.command()
def simulate_outage(
    minutes: float = typer.Option(6.0, help="Minutes of real failing checks"),
    interval: float = typer.Option(30.0, help="Seconds between checks during the outage"),
    config: str = typer.Option(None),
):
    """Real outage drill: point the poller at an unreachable API for N minutes.

    Uses a throw-away DB. The watchdog should post ONE loud @here message to the health
    webhook after `fail_alert_after_s`, then a recovery message once the real API is
    reachable again. Prints a timestamped timeline.
    """
    import tempfile
    from datetime import UTC, datetime
    from pathlib import Path

    from .scheduler import Scheduler

    cfg = load_config(config)
    setup_logging()
    cfg.settings.RADAR_DB_PATH = str(Path(tempfile.mkdtemp()) / "outage.db")
    cfg.settings.HEALTHCHECKS_PING_URL = ""  # drill must not touch the real dead-man switch
    bad = Scheduler(cfg, api_base="http://127.0.0.1:9")
    t0 = datetime.now(UTC)
    typer.echo(f"{t0.isoformat()} outage start (api unreachable for {minutes} min)")
    alerted_at = None
    while (datetime.now(UTC) - t0).total_seconds() < minutes * 60:
        bad.run_once()
        if alerted_at is None:
            with db_session(cfg.db_path) as conn:
                n = conn.execute(
                    "SELECT COUNT(*) n FROM health_events WHERE kind='failure_alert'"
                ).fetchone()["n"]
            if n:
                alerted_at = datetime.now(UTC)
                typer.echo(
                    f"{alerted_at.isoformat()} LOUD ALERT posted "
                    f"({(alerted_at - t0).total_seconds():.0f}s after first failure)"
                )
        time.sleep(interval)
    bad.shutdown()
    good = Scheduler(cfg)
    good.run_once()
    t1 = datetime.now(UTC)
    with db_session(cfg.db_path) as conn:
        rec = conn.execute(
            "SELECT detail FROM health_events WHERE kind='recovery'"
        ).fetchone()
    good.shutdown()
    typer.echo(f"{t1.isoformat()} real API restored; recovery event: {rec['detail'] if rec else 'none'}")


@app.command("publish-test-release")
def publish_test_release(
    tag: str = typer.Option(None, help="Tag name (default: vYYYYMMDD-HHMM)"),
    config: str = typer.Option(None),
):
    """Publish one synthetic release in the sandbox repo (latency harness)."""
    import httpx

    from .scripts_publish import publish_release

    cfg = load_config(config)
    if not cfg.settings.SANDBOX_REPO or not cfg.settings.SANDBOX_GITHUB_TOKEN:
        typer.echo("SANDBOX_REPO / SANDBOX_GITHUB_TOKEN not set", err=True)
        raise typer.Exit(1)
    if not tag:
        tag = "v" + time.strftime("%Y%m%d-%H%M%S")
    with httpx.Client(timeout=30) as client:
        rel = publish_release(
            client,
            cfg.settings.SANDBOX_REPO,
            cfg.settings.SANDBOX_GITHUB_TOKEN,
            tag,
        )
    typer.echo(f"Published release {tag} (id={rel.get('id')}) at {rel.get('published_at')}")


# Helper module for the publisher used by the CLI and the standalone script.
def _load_publisher():
    return None


if __name__ == "__main__":
    app()
